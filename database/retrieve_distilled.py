#!/usr/bin/env python3

import os
import json
import argparse
import numpy as np
from openai import OpenAI
from embed import get_text_embedding
from retrieve import query_index, INDEX_PATH_DEFAULT, MAPPING_PATH_DEFAULT
from contextlib import redirect_stdout
import sys

DEFAULT_MODEL = os.environ.get("ALTERNATIVE_COMPLETION_MODEL", "gpt-4o-mini")
CLIENT = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url="https://api.chatanywhere.tech/v1")


def call_model_distill(model, query_text, passage_text):
    # prompt = (
    #     "You are given a user query and a passage.\n"
    #     "Task: Extract only the information from the passage that directly answers or is relevant to the query.\n"
    #     "Requirements:\n"
    #     "- If there is no relevant information in the passage, respond exactly with: there is no relevant information\n"
    #     "- Otherwise produce a concise distilled report (1-3 short paragraphs) that uses only facts present in the passage.\n"
    #     "- Do not invent new facts or assumptions.\n"
    #     "- Start your answer with the prefix: DISTILLED:\n\n"
    #     f"User query:\n{query_text}\n\nPassage:\n{passage_text}\n\nRespond now."
    # )
    prompt = (
    "你将获得一个用户查询和一段文章内容。\n"
    "任务：从文章中提炼能够对回答问题产生贡献的信息。\n"
    "要求：\n"
    "- 如果文章中没有任何相关信息，请**严格**按以下内容回复：没有相关信息\n"
    "- 否则，请生成一份提炼报告，只能使用文章中明确给出的事实。\n"
    "- 不得编造任何新的事实或假设。\n"
    f"用户查询：\n{query_text}\n\n文章内容：\n{passage_text}\n\n现在开始回答。"
    )


    try:
        resp = CLIENT.responses.create(model=model, input=prompt)
        # prefer output_text convenience property if available
        text = getattr(resp, "output_text", None)
        if text is None:
            # fallback parsing
            out = resp.output if hasattr(resp, "output") else None
            if out and isinstance(out, list) and len(out) > 0:
                # each item may have 'content' list
                parts = []
                for item in out:
                    content = item.get("content") if isinstance(item, dict) else None
                    if content and isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict) and "text" in c:
                                parts.append(c["text"])
                            elif isinstance(c, str):
                                parts.append(c)
                text = "\n".join(parts)
            else:
                text = str(resp)
        return text.strip()
    except Exception as e:
        print("Model call failed:", e)
        return None


def cosine_sim(a, b):
    a = np.array(a, dtype=np.float32)
    b = np.array(b, dtype=np.float32)
    if a.ndim == 1:
        a = a / (np.linalg.norm(a) + 1e-12)
        b = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-12)
        return (b @ a).reshape(-1)
    else:
        return np.zeros((b.shape[0],), dtype=np.float32)


def retrieve_and_distill(index_path, mapping_path, query_text, top_k=5, model=DEFAULT_MODEL, filter_threshold=0.95):
    hits = query_index(index_path, mapping_path, query_text, top_k=top_k)
    if not hits:
        return []

    # Get embedding for canonical no-info phrase once
    # noinfo_phrase = "there is no relevant information"
    noinfo_phrase = "没有相关信息"
    noinfo_emb = get_text_embedding(noinfo_phrase)
    if noinfo_emb is None:
        print("Failed to compute no-info embedding; skipping filter")
        noinfo_emb = None
    else:
        noinfo_emb = np.array(noinfo_emb, dtype=np.float32)
        noinfo_emb = noinfo_emb / (np.linalg.norm(noinfo_emb) + 1e-12)

    distilled_results = []

    for hit in hits:
        key = hit.get("key")
        file_path = hit.get("file_path")

        # read passage content from file if available
        passage_text = None
        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as fh:
                    passage_text = fh.read()
            except Exception:
                passage_text = None

        if passage_text is None:
            # If content isn't available, skip this hit
            print(f"Warning: content for {key} not available, skipping")
            continue

        distilled = call_model_distill(model, query_text, passage_text)
        if distilled is None:
            print(f"Model failed for {key}, skipping")
            continue

        # Treat an exact match (case-insensitive) as no info
        if distilled.strip().lower().replace("。", "") == noinfo_phrase:
            sim_to_noinfo = 1.0
        else:
            emb = get_text_embedding(distilled)
            if emb is None or noinfo_emb is None:
                sim_to_noinfo = 0.0
            else:
                emb = np.array(emb, dtype=np.float32)
                emb = emb / (np.linalg.norm(emb) + 1e-12)
                sim_to_noinfo = float(np.dot(emb, noinfo_emb))

        if sim_to_noinfo >= filter_threshold:
            # Filtered out as too similar to 'no relevant information'
            print(f"Filtered (no info): {key} (sim={sim_to_noinfo:.3f})", file=sys.stderr, flush=True)
            continue

        distilled_results.append({
            "key": key,
            "file_path": file_path,
            "score": hit.get("score"),
            "distilled": distilled,
            "noinfo_similarity": sim_to_noinfo,
        })

    return distilled_results


def main():
    parser = argparse.ArgumentParser(description="Retrieve with FAISS and distill each passage via LLM, filtering 'no relevant information'")
    parser.add_argument("--index", default=INDEX_PATH_DEFAULT)
    parser.add_argument("--mapping", default=MAPPING_PATH_DEFAULT)
    parser.add_argument("--q", required=True, help="Query text")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--threshold", type=float, default=0.95, help="Cosine similarity threshold to filter 'no info' reports")
    args = parser.parse_args()

    res = retrieve_and_distill(args.index, args.mapping, args.q, top_k=args.k, model=args.model, filter_threshold=args.threshold)
    print(json.dumps(res, ensure_ascii=False, indent=2),flush=True)




if __name__ == "__main__":
    main()
