# Autonomous Research Agent

Lightweight research automation utilities: analysis + planning (LLM-driven), web search orchestration, and robust asynchronous scraping & extraction.

This repository contains three main components (scripts) that together form a simple pipeline for researching user queries:
- `planner.py` — Query analysis and research plan generation using a generative LLM (Google GenAI / Gemini in the current code).
- `searcher.py` — Executes the plan's search strategy across search APIs (Tavily primary) with a DuckDuckGo HTML fallback; scores and ranks results.
- `scraper.py` — Asynchronous, event-loop-safe scraper that fetches URLs, extracts text (HTML/PDF), detects paywalls, saves raw + cleaned contents into disk and SQLite.

This README describes each component, how they interact (architecture), configuration, and example usage.

---

## Architecture overview

High level flow:
1. User provides a natural-language research query to `planner.py`.
2. `planner.py` calls an LLM to:
   - produce a structured JSON analysis of the query (intent, scope, constraints, entities).
   - produce a structured research plan (sub-questions, search strategies, execution plan).
3. `searcher.py` consumes the plan and:
   - expands queries (variants), runs searches (Tavily API first, DuckDuckGo HTML fallback).
   - deduplicates, scores (relevance + domain quality), ranks results per sub-question and outputs a top-K set for each.
4. `scraper.py` takes URL lists (e.g., top results from `searcher`) and:
   - fetches pages (with concurrency limits and retries), saves raw HTML/PDF,
   - extracts clean text (trafilatura → readability → BeautifulSoup fallbacks; pdfminer for PDFs),
   - detects paywalls and stores cleaned results and metadata into a SQLite DB and filesystem.

Sequence (simplified):
planner.py (LLM) -> research plan JSON -> searcher.py (search + ranking) -> list of candidate URLs -> scraper.py (fetch + extract + store)

---

## Component details

### planner.py
- Purpose: Convert a user research query into:
  - a JSON "query analysis" (intent, scope, constraints, entities, scores),
  - a JSON "research plan" with `sub_questions` and `search_strategy` for each sub-question.
- Implementation highlights:
  - Uses `google.genai` SDK to call `gemini-2.5-flash` (configurable by MODEL_NAME).
  - Two prompt builders: `build_analysis_prompt(query)` and `build_planning_prompt(query, analysis_json)` that ask the model to return strict JSON.
  - `run_model(prompt)` wraps the model invocation.
- Important notes:
  - The example script sets `query = "What is the reason of US recession"`. Modify this or integrate with an external interface.
  - The output JSON keys to expect: `research_strategy`, `sub_questions` (each with `id`, `question`, `search_strategy`, etc.), and `execution_plan`.
  - Environment variable: `GEMINI_API_KEY` (loaded via `.env`).

### searcher.py
- Purpose: Execute search queries defined in the plan and return ranked candidate documents for each sub-question.
- Search sources:
  - Primary: Tavily API (`TAVILY_API_KEY` required). Endpoint: `https://api.tavily.com/search`.
  - Fallback: DuckDuckGo HTML scraping (`html.duckduckgo.com/html/`).
- Key functions:
  - `duckduckgo_search(session, query, max_results)`: parses DDG HTML with BeautifulSoup.
  - `tavily_search(session, query, max_results)`: uses Tavily JSON API.
  - `relevance_score(query, title, snippet)`: a simple keyword-match based relevance function.
  - `domain_quality(url)`: small domain reputation scoring (GOOD_DOMAINS / BAD_DOMAINS lists).
  - `run_searcher_for_subquestion(...)`: runs queries, dedupes, scores, ranks, and returns top results (default top 10).
  - `run_searcher_for_all(subquestions)`: runs sub-question searches in parallel via asyncio.gather.
- Integration with planner:
  - `searcher.py` imports `plan` from `planner.py` via `from planner import plan as plan_output`. When imported, `planner.py` executes and generates `plan`. Alternatively, you can create and pass a saved plan JSON into searcher (recommended for production workflows to avoid regenerating a plan on import).
- Output:
  - JSON of per-sub-question results and a `search_results.json` file when run as a script.

### scraper.py
- Purpose: Robust async scraper + extractor for the candidate URLs produced by the searcher.
- Features:
  - Async fetching with `aiohttp`, concurrency control via semaphores and connectors, retry/backoff policy.
  - Safe saving of raw files and cleaned text to filesystem (`data/raw`, `data/clean`) and metadata into `scraper.db` (SQLite).
  - Extraction pipeline:
    - Best effort: `trafilatura` (if installed) → `readability` → BeautifulSoup fallback.
    - PDF extraction with `pdfminer` (if available).
  - Paywall detection heuristics to mark paywalled pages.
  - Fingerprinting and lightweight summarization for storage.
- Usage:
  - CLI mode expects a JSON file of tasks (list of objects with keys `id`, `url`, `sub_question`, `meta`).
  - Example task:
    ```json
    { "id": "u1", "url": "https://example.org/article", "sub_question": "q1", "meta": {} }
    ```
  - Produces `scrape_results.json` and stores raw/clean files and SQLite records.

---

## Configuration / Environment

Create a `.env` file (or set environment variables) with:

- GEMINI_API_KEY - API key for the Google GenAI SDK (if using planner).
- TAVILY_API_KEY - API key for Tavily (used by searcher).

Other settings are in-file as top-level constants in each script:
- `scraper.py` settings: `RAW_STORAGE_DIR`, `CLEAN_STORAGE_DIR`, `DB_FILE`, `MAX_CONCURRENT`, etc.
- `searcher.py` constants: `TAVILY_URL`, `HEADERS`, domain lists, timeouts.

---

## Quickstart examples

1. Install dependencies (approximate):
   ```
   pip install aiohttp aiofiles beautifulsoup4 python-dotenv google-genai trafilatura readability-lxml pdfminer.six
   ```
   Note: Some libraries are optional (trafilatura, readability, pdfminer); scraper uses fallbacks if they're not present.

2. Generate a plan (basic):
   - Edit `planner.py` to set your `query` string or wire an interactive input.
   - Set `GEMINI_API_KEY` in `.env`.
   - Run:
     ```
     python planner.py
     ```
   - Copy the printed "RESEARCH PLAN" JSON into `plan.json` (or adapt the workflow to persist it automatically).

3. Run searcher with a saved plan:
   - Option A (quick but causes planner to run inside searcher): just run:
     ```
     python searcher.py
     ```
     (It imports `planner` which generates `plan` — this may call the LLM again.)
   - Option B (recommended): modify `searcher.py` to load `plan.json` into the variable used by `clean_llm_json`, or replace `plan_output` with the JSON string from file, then run:
     ```
     python searcher.py
     ```

4. Scrape URLs:
   - Prepare tasks JSON (list of `{id, url, sub_question, meta}`).
   - Run:
     ```
     python scraper.py --input tasks.json --outdir data
     ```
   - Results and DB are written under `data/`.

---

## Notes & Next steps / Improvements

- planner.py currently expects to call Gemini via `google.genai`. You can replace with another LLM or local chain if desired.
- `searcher.py` relies on an external Tavily API. If unavailable, it falls back to DuckDuckGo HTML search. Consider adding Bing/Google custom search integrations.
- The `planner -> searcher` handoff is currently done by importing `planner` in `searcher.py`. For robust pipelines, persist the plan to disk and have searcher read it (avoids repeated LLM calls).
- Add unit tests and CI, sanitize/validate LLM outputs robustly (current code expects valid JSON and contains utilities to clean fence-marked LLM output).
- Improve paywall detection and add heuristics for paywalled summary scraping (e.g., via metadata or cached previews).

---

## Files in repo (primary)
- planner.py — LLM-based query analysis & plan generation.
- searcher.py — Search orchestration (Tavily + DuckDuckGo fallback), scoring, ranking.
- scraper.py — Async scraper, extraction pipeline, storage & DB.
- (Other small utilities and configs may exist in the repository.)

---
