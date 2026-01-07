# Database Documentation

**Overview**
- **Purpose:** Documentation for the retrieval components used in the RAG pipeline: `retrieve.py` and `retrieve_distilled.py`.
- **Scope:** How to run the scripts, what files they use, and how the distilled retrieval post-processes model output.

**Files**
- **`build_db.py`:** Builds a FAISS index (`vector_index.faiss`) and a mapping JSON (`vector_mapping.json`) from plain-text files under the `passages/` directory. Logs embedding failures to `embed_errors.csv` by default.
- **`retrieve.py`:** Loads the FAISS index and mapping, embeds a query via `get_text_embedding()` and returns the top-k nearest passages.
- **`retrieve_distilled.py`:** Calls `retrieve.py` to get candidates, asks an LLM to distill each passage with respect to the original query, and filters out "no relevant information" responses using embedding similarity.

**Quick Usage**
- Build the FAISS index (run once or when adding passages):

```bash
python3 build_db.py --passages passages
```

- Retrieve top-k passages:

```bash
python3 retrieve.py --q "your query here" --k 5
```

- Retrieve and distill (LLM calls per hit):

```bash
python3 retrieve_distilled.py --q "your query here" --k 5 --threshold 0.95
```

**How `retrieve.py` works**
- **Load index & mapping:** Opens `vector_index.faiss` (FAISS index) and `vector_mapping.json` (ordered list of keys and metadata).
- **Embed query:** Uses `get_text_embedding()` from `embed.py` to produce a vector for the query.
- **Search:** Performs a FAISS search (inner-product on normalized vectors) to return top-k indices and similarity scores.
- **Map results:** Maps FAISS indices to filenames/metadata from the mapping file and returns `key`, `score`, and `file_path` for each hit.

**How `retrieve_distilled.py` works**
- **Step 1 — Retrieve:** Calls `query_index()` (from `retrieve.py`) to get top-k hits.
- **Step 2 — Read passages:** For each hit, reads the original passage text from `file_path` on disk.
- **Step 3 — Distill via LLM:** Sends a focused prompt to the LLM asking it to extract only the information from the passage that directly answers or is relevant to the query. The prompt instructs the model to reply with a canonical no-info phrase (currently in Chinese: "没有相关信息") if nothing relevant exists.
- **Step 4 — Filter no-info:** Embeds the distilled report, computes cosine similarity to the canonical no-info embedding, and drops the report if similarity >= `--threshold` (default 0.95). Exact textual matches to the canonical phrase are also treated as no-info.
- **Step 5 — Return:** Outputs a JSON array of distilled results with `key`, `file_path`, `score`, `distilled` (text), and `noinfo_similarity` (float).

**Canonical no-info handling**
- The distilled retriever uses a canonical phrase to represent absence of relevant information. This phrase is embedded once and used as a filter.
- Two filtering modes:
  - Exact textual match to the canonical phrase — treated as no-info immediately.
  - Embedding similarity to the canonical phrase — if >= `--threshold`, the distilled report is filtered out.

**Embedding failure logging (from `build_db.py`)**
- Failures to embed a passage are appended to `embed_errors.csv` (or the file path set by `ERROR_CSV_PATH`). The CSV columns are: `filename`, `datetime` (UTC ISO), and `error_message`.
- On subsequent runs, the builder will skip files present in the CSV and print a distinct message: "Skipping previously-failed: <filename> (see embed_errors.csv)".

**Configuration & Environment**
- `OPENAI_API_KEY`: required for LLM calls used by `retrieve_distilled.py`.
- `ALTERNATIVE_COMPLETION_MODEL`: optional environment var to override the default model used by `retrieve_distilled.py`.
- `ERROR_CSV_PATH`: optional environment var to change the CSV path used by `build_db.py`.
- CLI flags available across scripts: `--index` and `--mapping` to override default index/mapping filenames, `--k` for top-k, and `--threshold` for no-info filtering.

**Practical notes & tuning**
- `retrieve_distilled.py` makes one LLM call per retrieved passage — expect costs and latency proportional to `k`.
- If too many false positives/negatives occur in filtering, tune `--threshold` or adjust the canonical no-info phrase and prompt wording.
- For multilingual datasets, ensure the prompt and canonical phrase match the language of queries and passages.

**Example workflow**
1. Add or update text files in `passages/`.
2. Run `python3 build_db.py --passages passages` to index new files (skips already indexed and previously-failed files).
3. Run `python3 retrieve_distilled.py --q "your query" --k 3` to get distilled, filtered answers.
