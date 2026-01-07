# Copilot instructions — Open Deep Research

This file contains concise, actionable guidance for AI coding agents working in this repository. Focus on observable patterns and concrete commands.

- **Project purpose**: an iterative, LLM-driven research assistant that generates SERP queries, scrapes results (via Firecrawl), produces structured learnings, and composes final markdown reports. See [README.md](README.md).

- **How to run (local dev)**: use `npm start` (runs `tsx --env-file=.env.local src/run.ts`) for the interactive CLI; use `npm run api` to start the HTTP API (`src/api.ts`). See `package.json` scripts.

- **Docker**: image built with `Dockerfile`. Use `docker compose up -d` then `docker exec -it deep-research npm run docker` per README instructions. Env file is `.env.local`.

- **Important env vars**:
  - `FIRECRAWL_KEY` and optional `FIRECRAWL_BASE_URL` — used by `src/deep-research.ts` via `@mendable/firecrawl-js`.
  - `OPENAI_KEY`, `OPENAI_ENDPOINT` — used by `src/ai/providers.ts` (o3-mini fallback). If you want a custom model use `CUSTOM_MODEL`.
  - `FIREWORKS_KEY` — enables `deepseek-r1` model in `src/ai/providers.ts`.
  - `FIRECRAWL_CONCURRENCY` — controls `ConcurrencyLimit` in `src/deep-research.ts` (default 2).
  - `FIRECRAWL_SOURCES` — number of markdown results to pull from Firecrawl per SERP query (set to `0` to disable Firecrawl during testing).
  - `INTERNAL_SOURCES` — number of internal DB (FAISS) distilled results to fetch per SERP query (uses `database/retrieve_distilled.py`).
  - `DR_LANG` — set to `CN` to switch system prompts and prompt snippets to Chinese. Defaults to English when unset.

- **Model selection logic (critical)**: `src/ai/providers.ts` picks in order: `CUSTOM_MODEL` → `FIREWORKS_KEY` (deepSeek R1) → OpenAI `o3-mini`. If no provider is configured the code throws. Don't change this ordering without updating `getModel()` usages.

- **Key components & responsibilities**:
  - `src/run.ts`: interactive CLI, collects breadth/depth, writes `report.md` or `answer.md`.
  - `src/api.ts`: HTTP endpoints — POST `/api/research` expects `{query, depth, breadth}` and returns `{answer, learnings, visitedUrls}`; POST `/api/generate-report` returns the report string.
  - `src/deep-research.ts`: core recursion, query generation, Firecrawl calls, result processing, uses `generateObject` with Zod schemas for structured outputs.
  - `src/prompt.ts`: system prompt used across generations — changes here alter agent behaviour globally.
  - `src/ai/providers.ts`: wires model providers and contains `trimPrompt()` logic (token-aware trimming).

- **Structured outputs**: many LLM calls use `generateObject` with explicit Zod schemas (see `generateSerpQueries`, `processSerpResult`, `writeFinalReport`). Keep schemas and expected keys intact when changing prompts.

- **Search & scrape**: `deep-research` calls `firecrawl.search(..., { scrapeOptions: { formats: ['markdown'] }})` and expects `result.data[].markdown`. Tests or changes that alter Firecrawl response shape must be coordinated.

- **Hybrid retrieval**: The research pipeline now supports a hybrid retrieval model (Firecrawl + internal FAISS-based retriever). `FIRECRAWL_SOURCES` and `INTERNAL_SOURCES` control how many hits are taken from each source per SERP query. The internal retriever is driven by `database/retrieve_distilled.py` which returns JSON (`distilled` text + `file_path`).

- **Concurrency & rate-limits**: code uses `p-limit` and the `FIRECRAWL_CONCURRENCY` env var. Prefer changing the env var over modifying concurrency constants.

- **Persistence & outputs**: final artifacts are written to `report.md` or `answer.md`. The vector DB utilities live under `database/` (Python FAISS scripts). See [database/README.md](database/README.md) for building/querying embeddings.

- **Developer conventions**:
  - Run TypeScript files with `tsx` (no build step). Use `npm run format` to apply Prettier.
  - Keep structured-output schemas stable; prefer extending prompts over reshaping schemas.
  - System-level behaviour is centralized in `src/prompt.ts` — update there for global LLM style changes.

- **APIs & examples**:
  - Example curl for research: `curl -X POST http://localhost:3051/api/research -H 'Content-Type: application/json' -d '{"query":"X","depth":2,"breadth":3}'`

- **Debugging tips**:
  - When model selection fails, inspect `process.env` for `OPENAI_KEY`, `FIREWORKS_KEY`, or `CUSTOM_MODEL`.
  - Timeouts in Firecrawl show up as thrown errors in `deep-research.ts` (catch logs); increase `timeout` or reduce `FIRECRAWL_CONCURRENCY`.
  - For long prompts/overflow issues, examine `trimPrompt()` and `encoder` usage in `src/ai/providers.ts`.

- **Files to inspect for behavior changes**:
  - [src/deep-research.ts](src/deep-research.ts) — recursion, concurrency, Firecrawl usage
  - [src/ai/providers.ts](src/ai/providers.ts) — model wiring and trimming
  - [src/prompt.ts](src/prompt.ts) — system prompt
  - [src/run.ts](src/run.ts) and [src/api.ts](src/api.ts) — entrypoints
  - [database/README.md](database/README.md) — vector db utilities

If anything here is unclear or you want me to expand an area (API examples, common edits, or adding unit-test guidance), tell me which part to iterate on.
