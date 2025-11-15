# Autonomous Research Agent

An intelligent multi-stage research automation system that takes a user query, breaks it down into sub-questions, searches the web for relevant information, and scrapes content for comprehensive analysis.

## Architecture Overview

The system operates through a sequential pipeline of four main stages:

```
User Query → Stage 1: Planning → Stage 2: Searching → Stage 2.5: Bridge → Stage 3: Scraping → Results
```

---

## Stage 1: Query Analysis & Planning (`planner.py`)

**Purpose:** Analyze the user's research query and create a structured research plan with sub-questions.

### Key Components:

1. **Query Analysis**
   - Extracts structured information from the user query
   - Identifies primary intent (information seeking, causal analysis, comparison, etc.)
   - Determines scope (breadth, depth, specificity)
   - Identifies domains, constraints (temporal, geographic), and entities
   - Calculates complexity score (1-5)

2. **Research Planning**
   - Creates actionable sub-questions based on the analysis
   - Defines search strategies for each sub-question
   - Plans execution phases (foundation, deep dive, verification)
   - Sets success criteria and synthesis guidance

### Technology Stack:
- **LLM:** Google Gemini 2.5 Flash (via `google-genai`)
- **Configuration:** Loads API key from `.env` file

### Input/Output:
- **Input:** User research query (string)
- **Output:** JSON object containing:
  - Query analysis (intent, scope, domains, constraints)
  - Sub-questions with search strategies
  - Execution plan with phases
  - Success criteria

### Example Query:
```python
query = "What is the reason of US recession"
```

The planner generates structured JSON with multiple sub-questions like:
- "What are the economic indicators of recession?"
- "What are the historical causes of US recessions?"
- "What are current factors contributing to recession?"

---

## Stage 2: Web Search (`searcher.py`)

**Purpose:** Execute web searches for each sub-question and collect relevant URLs with metadata.

### Key Components:

1. **Search Engine Integration**
   - **Primary:** Tavily API (advanced search depth)
   - **Fallback:** DuckDuckGo HTML scraping (when Tavily fails)

2. **Query Execution**
   - Processes multiple search queries per sub-question
   - Uses query variants (academic, general, temporal)
   - Executes searches in parallel with async/await
   - Rate limiting (0.5s delay between requests)

3. **Result Ranking**
   - **Relevance Scoring:** Keyword matching between query and results
   - **Domain Quality Scoring:** Prioritizes authoritative sources
     - Good domains: `.gov`, `.edu`, research institutions, news outlets
     - Bad domains: `quora`, `reddit`, low-quality content farms
   - **Final Score:** Combines relevance + domain quality

4. **Result Deduplication**
   - Removes duplicate URLs across queries
   - Keeps top 10 results per sub-question

### Technology Stack:
- **HTTP Client:** `aiohttp` (async HTTP requests)
- **HTML Parsing:** `BeautifulSoup4` (DuckDuckGo fallback)
- **APIs:** Tavily Search API

### Input/Output:
- **Input:** Research plan JSON from Stage 1 (sub-questions with search strategies)
- **Output:** `search_results.json` containing:
  - Sub-question ID and text
  - Query execution details
  - Top-ranked URLs with metadata (title, snippet, scores)

### Example Output Structure:
```json
[
  {
    "sub_question_id": "q1",
    "sub_question_text": "What are the economic indicators...",
    "queries_executed": [...],
    "total_results_found": 45,
    "results": [
      {
        "url": "https://example.gov/...",
        "title": "...",
        "snippet": "...",
        "rank_score": 0.95,
        "relevance_score": 0.85,
        "domain_score": 0.3
      }
    ]
  }
]
```

---

## Stage 2.5: Data Bridge (`bridge_searcher_scrapper.py`)

**Purpose:** Convert searcher output format to scraper input format and manage data flow between stages.

### Key Components:

1. **Format Conversion**
   - Transforms search results into scraper tasks
   - Generates unique IDs for each URL
   - Preserves metadata (scores, sub-question context)

2. **URL Deduplication**
   - Ensures each URL is scraped only once across all sub-questions
   - Tracks URLs with hash set

3. **Result Filtering**
   - Allows filtering to top N results per sub-question (default: 5)
   - Reduces scraping workload

### Technology Stack:
- Pure Python (JSON processing, hashlib for ID generation)

### Input/Output:
- **Input:** `search_results.json` from Stage 2
- **Output:** `scraper_input.json` with format:
```json
[
  {
    "id": "abc123def456",
    "url": "https://example.com/...",
    "sub_question": "q1",
    "meta": {
      "sub_question_text": "...",
      "title": "...",
      "snippet": "...",
      "rank_score": 0.95,
      "rank_in_results": 1
    }
  }
]
```

---

## Stage 3: Content Scraping (`scraper.py`)

**Purpose:** Fetch and extract clean text content from URLs for analysis.

### Key Components:

1. **HTTP Fetching**
   - Async fetching with retry logic (2 retries)
   - Timeout: 20 seconds
   - Concurrency control: 5 concurrent requests
   - User-Agent spoofing for politeness
   - File size limits (10MB max)

2. **Text Extraction**
   - **HTML Content:**
     - Primary: `trafilatura` (best quality extraction)
     - Fallback: `readability-lxml` (article extraction)
     - Last resort: `BeautifulSoup` (basic text extraction)
   - **PDF Content:** `pdfminer` for PDF text extraction

3. **Paywall Detection**
   - Keyword-based heuristics (subscribe, paywall, members-only)
   - Length-based checks (suspiciously short content)
   - Flags paywalled content but still saves what's available

4. **Storage**
   - **Raw Storage:** Saves original HTML/PDF to `data/raw/`
   - **Clean Storage:** Saves extracted text to `data/clean/`
   - **Database:** SQLite (`scraper.db`) tracks metadata:
     - `raw_pages`: URL, fetch time, content type, HTTP status
     - `cleaned_pages`: Title, language, word count, text fingerprint

5. **Content Fingerprinting**
   - SHA256 hash of text content
   - Detects duplicate content across URLs

### Technology Stack:
- **HTTP Client:** `aiohttp` (async requests)
- **Text Extraction:** `trafilatura`, `readability-lxml`, `BeautifulSoup4`
- **PDF Processing:** `pdfminer`
- **Storage:** SQLite3, filesystem (organized by domain)
- **Async I/O:** `aiofiles` for non-blocking file operations

### Input/Output:
- **Input:** `scraper_input.json` from Stage 2.5
- **Output:** 
  - `data/raw/`: Original HTML/PDF files
  - `data/clean/`: Extracted text files
  - `scraper.db`: SQLite database with metadata
  - `scrape_results.json`: Status report for each URL

### Example Result:
```json
{
  "id": "abc123def456",
  "url": "https://example.com/...",
  "status": "ok",
  "clean_path": "data/clean/example_com_article_abc123.txt",
  "raw_path": "data/raw/example_com_article_abc123.html",
  "title": "Economic Analysis of...",
  "lang": "en",
  "summary": "First 400 characters...",
  "fingerprint": "sha256hash..."
}
```

---

## Data Flow

```
1. User Query
   ↓
2. planner.py
   - Analyzes query
   - Creates sub-questions
   → Output: plan with search strategies
   ↓
3. searcher.py
   - Searches web (Tavily/DuckDuckGo)
   - Ranks results
   → Output: search_results.json
   ↓
4. bridge_searcher_scrapper.py
   - Converts format
   - Deduplicates URLs
   → Output: scraper_input.json
   ↓
5. scraper.py
   - Fetches URLs
   - Extracts text
   - Stores in database
   → Output: data/raw/, data/clean/, scraper.db
   ↓
6. Analysis/Synthesis (future stage)
   - Combines scraped content
   - Generates final answer
```

---

## Setup & Installation

### Prerequisites:
- Python 3.8+
- API Keys:
  - Google Gemini API key (for planner)
  - Tavily API key (for searcher)

### Installation:

1. **Clone the repository:**
```bash
git clone https://github.com/1byinf8/Autonomus-Research-Agent-.git
cd Autonomus-Research-Agent-
```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
```

3. **Create `.env` file:**
```bash
# .env
GEMINI_API_KEY=your_gemini_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here
```

### Dependencies:
```
google-genai          # Gemini LLM integration
aiohttp==3.9.1        # Async HTTP client
beautifulsoup4==4.12.2 # HTML parsing
python-dotenv==1.0.0  # Environment variable management
```

Optional (for enhanced scraping):
- `trafilatura` - Best text extraction
- `readability-lxml` - Article extraction
- `pdfminer.six` - PDF text extraction

---

## Usage

### Running the Full Pipeline:

**Step 1: Generate Research Plan**
```bash
python planner.py
```
- Modify the `query` variable in `planner.py`
- Outputs analysis and research plan to console

**Step 2: Execute Web Searches**
```bash
python searcher.py
```
- Reads plan from `planner.py` (imported)
- Outputs: `search_results.json`

**Step 3: Convert to Scraper Format**
```bash
python bridge_searcher_scrapper.py
```
- Reads: `search_results.json`
- Outputs: `scraper_input.json`

**Step 4: Scrape Content**
```bash
python scraper.py --input scraper_input.json --outdir data
```
- Outputs: `data/raw/`, `data/clean/`, `scraper.db`, `scrape_results.json`

---

## Key Features

### Intelligent Query Processing
- Multi-level query analysis
- Automatic sub-question generation
- Context-aware search strategies

### Robust Search
- Dual search engine support (Tavily + DuckDuckGo)
- Quality-based domain ranking
- Relevance scoring

### Advanced Scraping
- Multi-format support (HTML, PDF)
- Paywall detection
- Content deduplication
- Retry logic and error handling

### Scalable Architecture
- Async/await for concurrent operations
- Rate limiting and politeness delays
- Database-backed storage
- Modular stage design

---

## File Structure

```
Autonomus-Research-Agent-/
├── planner.py                    # Stage 1: Query analysis & planning
├── searcher.py                   # Stage 2: Web search
├── bridge_searcher_scrapper.py   # Stage 2.5: Format conversion
├── scraper.py                    # Stage 3: Content scraping
├── requirements.txt              # Python dependencies
├── README.md                     # This file
├── .env                          # API keys (not committed)
├── .gitignore                    # Git ignore rules
├── search_results.json           # Output from searcher
├── scraper_input.json            # Output from bridge
├── scraper.db                    # SQLite database
└── data/                         # Scraped content (not committed)
    ├── raw/                      # Original HTML/PDF files
    └── clean/                    # Extracted text files
```

---

## Future Enhancements

1. **Stage 4: Content Synthesis**
   - LLM-based answer generation
   - Citation management
   - Confidence scoring

2. **Improved Search**
   - Google Scholar integration
   - Academic paper parsing
   - Semantic search

3. **Enhanced Scraping**
   - JavaScript rendering (Playwright/Selenium)
   - Better paywall bypass
   - Image/table extraction

4. **Performance**
   - Caching layer (Redis)
   - Distributed scraping
   - Progress tracking UI

---

## License

[Add your license information here]

## Contributing

[Add contribution guidelines here]

## Contact

[Add contact information here]
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
