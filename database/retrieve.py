#!/usr/bin/env python3

import os
import json
import argparse
import numpy as np
import faiss
from embed import get_text_embedding


INDEX_PATH_DEFAULT = "vector_index.faiss"
MAPPING_PATH_DEFAULT = "vector_mapping.json"


def load_mapping(mapping_path):
    if not os.path.exists(mapping_path):
        return {"keys": [], "meta": {}}
    with open(mapping_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def query_index(index_path, mapping_path, query_text, top_k=5):
    if not os.path.exists(index_path) or not os.path.exists(mapping_path):
        print("Index or mapping not found. Run build_db.py first.")
        return []

    mapping = load_mapping(mapping_path)
    keys = mapping.get("keys", [])
    if not keys:
        print("Index mapping is empty")
        return []

    idx = faiss.read_index(index_path)

    q_emb = get_text_embedding(query_text)
    if q_emb is None:
        print("Failed to embed query")
        return []
    q = np.array(q_emb, dtype=np.float32)
    q = q / (np.linalg.norm(q) + 1e-12)

    D, I = idx.search(q.reshape(1, -1), top_k)
    results = []
    for score, iid in zip(D[0], I[0]):
        if iid < 0 or iid >= len(keys):
            continue
        key = keys[int(iid)]
        meta = mapping.get("meta", {}).get(key, {})
        results.append({"key": key, "score": float(score), "file_path": meta.get("file_path"), "meta": meta})
    return results


def main():
    parser = argparse.ArgumentParser(description="Query the FAISS vector index")
    parser.add_argument("--index", default=INDEX_PATH_DEFAULT, help="FAISS index file to use")
    parser.add_argument("--mapping", default=MAPPING_PATH_DEFAULT, help="JSON mapping file")
    parser.add_argument("--q", required=True, help="Query text")
    parser.add_argument("--k", type=int, default=5, help="Top k results")
    args = parser.parse_args()

    results = query_index(args.index, args.mapping, args.q, top_k=args.k)
    for r in results:
        print(f"{r['key']}: score={r['score']:.4f} file={r['file_path']}")


if __name__ == "__main__":
    main()
