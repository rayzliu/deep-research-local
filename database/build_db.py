#!/usr/bin/env python3

import os
import glob
import csv
from datetime import datetime
import argparse
import time
import json
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


def save_mapping(mapping, mapping_path):
    with open(mapping_path, "w", encoding="utf-8") as fh:
        json.dump(mapping, fh, ensure_ascii=False)


def init_or_load_index(index_path, mapping_path):
    mapping = load_mapping(mapping_path)
    if os.path.exists(index_path) and mapping.get("keys"):
        idx = faiss.read_index(index_path)
        return idx, mapping
    else:
        return None, mapping


def normalize(vec: np.ndarray):
    norm = np.linalg.norm(vec)
    if norm == 0:
        return vec
    return vec / norm


def process_passages(passages_dir, index_path, mapping_path, skip_existing=True):
    files = sorted(glob.glob(os.path.join(passages_dir, "*.txt")))
    if not files:
        print(f"No .txt files found in {passages_dir}")
        return

    idx, mapping = init_or_load_index(index_path, mapping_path)
    error_csv = os.environ.get("ERROR_CSV_PATH", "embed_errors.csv")

    # load previously failed files from CSV
    failed_files = set()
    if os.path.exists(error_csv):
        try:
            with open(error_csv, newline="", encoding="utf-8") as ef:
                reader = csv.DictReader(ef)
                for row in reader:
                    fname = row.get("filename")
                    if fname:
                        failed_files.add(fname)
        except Exception:
            # if CSV is corrupted/unreadable, ignore and continue
            failed_files = set()

    for fpath in files:
        key = os.path.basename(fpath)
        if key in failed_files:
            print(f"Skipping previously-failed: {key} (see {error_csv})")
            continue

        if skip_existing and key in mapping["keys"]:
            print(f"Skipping existing: {key}")
            continue

        with open(fpath, "r", encoding="utf-8") as fh:
            content = fh.read()

        print(f"Embedding: {key}...")
        try:
            emb = get_text_embedding(content)
            # if emb is None:
            #     raise RuntimeError("embedding returned None")
        except Exception as e:
            err_msg = str(e)
            print(f"Error embedding {key}: {err_msg}")
            # append to CSV
            try:
                write_header = not os.path.exists(error_csv)
                with open(error_csv, "a", newline="", encoding="utf-8") as ef:
                    writer = csv.DictWriter(ef, fieldnames=["filename", "datetime", "error_message"])
                    if write_header:
                        writer.writeheader()
                    writer.writerow({
                        "filename": key,
                        "datetime": datetime.utcnow().isoformat() + "Z",
                        "error_message": err_msg,
                    })
            except Exception:
                print(f"Failed to write to error CSV: {error_csv}")
            continue

        vec = np.array(emb, dtype=np.float32)
        vec = normalize(vec)

        if idx is None:
            dim = vec.shape[0]
            idx = faiss.IndexFlatIP(dim)

        idx.add(vec.reshape(1, -1))

        mapping["keys"].append(key)
        mapping["meta"][key] = {"file_path": fpath, "created_at": time.time()}

        # Persist index and mapping after each add to be safe
        faiss.write_index(idx, index_path)
        save_mapping(mapping, mapping_path)
        print(f"Stored: {key}")


def main():
    parser = argparse.ArgumentParser(description="Build a FAISS vector index from text files in a folder")
    parser.add_argument("--passages", default="passages", help="Path to passages folder")
    parser.add_argument("--index", default=INDEX_PATH_DEFAULT, help="FAISS index file to create/use")
    parser.add_argument("--mapping", default=MAPPING_PATH_DEFAULT, help="JSON mapping file to store keys/meta")
    parser.add_argument("--no-skip", dest="skip", action="store_false", help="Do not skip existing keys")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.index) or ".", exist_ok=True)
    process_passages(args.passages, args.index, args.mapping, skip_existing=args.skip)


if __name__ == "__main__":
    main()
