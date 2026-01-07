# Vector DB builder and retriever (FAISS)

Usage:

- Build the FAISS index (skips existing keys by default):

```bash
python3 build_db.py --passages passages --index vector_index.faiss --mapping vector_mapping.json
```

- Query the FAISS index:

```bash
python3 retrieve.py --index vector_index.faiss --mapping vector_mapping.json --q "your query here" --k 3
```

Notes:
- The scripts use `get_text_embedding` from `embed.py` (already present).
- Embeddings are stored in a FAISS index (`vector_index.faiss`) and a mapping JSON (`vector_mapping.json`).
- No chunking is performed; each file is embedded whole and keyed by filename (filename used as the key in the mapping).

Files created/used:

- `vector_index.faiss`: FAISS index persisted to disk
- `vector_mapping.json`: JSON file mapping index ids to filenames and metadata
