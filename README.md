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
