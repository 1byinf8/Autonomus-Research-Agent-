#!/usr/bin/env python3
"""
Fixed Ultra-Agent Scraper - Event Loop Safe
Key fixes:
- Removed nested event loops
- Better error handling
- Fixed asyncio compatibility issues
"""
import asyncio
import aiohttp
import aiofiles
import os
import time
import json
import hashlib
import sqlite3
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

# Optional dependencies
try:
    import trafilatura
except Exception:
    trafilatura = None

try:
    from readability import Document as ReadabilityDocument
except Exception:
    ReadabilityDocument = None

# PDF extraction
try:
    from pdfminer.high_level import extract_text as pdf_extract_text
except Exception:
    pdf_extract_text = None

# -----------------------
# CONFIG
# -----------------------
RAW_STORAGE_DIR = "data/raw"
CLEAN_STORAGE_DIR = "data/clean"
DB_FILE = "scraper.db"
MAX_CONCURRENT = 5                     # Concurrent requests
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)
USER_AGENT = "AutonomousResearchAgent/1.0 (+https://example.org)"
CHUNK_SIZE = 2000
MAX_RETRIES = 2
DELAY_BETWEEN_REQUESTS = 0.5          # seconds

# Paywall detection keywords
PAYWALL_KEYWORDS = [
    "subscribe", "subscription", "paywall", "members-only",
    "sign up to continue", "create an account", "login to read"
]

# -----------------------
# STORAGE: SQLite
# -----------------------
db_lock = asyncio.Lock()

def init_db():
    """Initialize SQLite database"""
    con = sqlite3.connect(DB_FILE, check_same_thread=False)
    cur = con.cursor()
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS raw_pages (
        id TEXT PRIMARY KEY,
        url TEXT,
        fetched_at REAL,
        content_type TEXT,
        path TEXT,
        http_status INTEGER
    )
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS cleaned_pages (
        id TEXT PRIMARY KEY,
        url TEXT,
        title TEXT,
        text_path TEXT,
        summary TEXT,
        lang TEXT,
        fingerprint TEXT,
        word_count INTEGER
    )
    """)
    
    con.commit()
    return con

# Initialize DB at module load
DB = init_db()

# -----------------------
# UTILITIES
# -----------------------
def safe_filename(url: str) -> str:
    """Generate safe filename from URL"""
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    parsed = urlparse(url)
    name = (parsed.path.strip("/").replace("/", "_") or "root")[:80]
    # Remove special chars
    name = "".join(c for c in name if c.isalnum() or c in "-_")
    return f"{parsed.netloc}_{name}_{h}"

def ensure_dirs():
    """Create necessary directories"""
    os.makedirs(RAW_STORAGE_DIR, exist_ok=True)
    os.makedirs(CLEAN_STORAGE_DIR, exist_ok=True)

def is_pdf_url(url: str, content_type: Optional[str] = None) -> bool:
    """Check if URL is PDF"""
    if content_type and "pdf" in content_type.lower():
        return True
    return url.lower().endswith(".pdf")

def fingerprint_text(text: str) -> str:
    """Generate fingerprint of text content"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

# -----------------------
# FETCH
# -----------------------
async def fetch_url(session: aiohttp.ClientSession, url: str) -> Tuple[Optional[bytes], Optional[str], int]:
    """Fetch URL with retries"""
    headers = {"User-Agent": USER_AGENT}
    
    for attempt in range(MAX_RETRIES + 1):
        try:
            async with session.get(url, headers=headers, timeout=REQUEST_TIMEOUT) as resp:
                status = resp.status
                ct = resp.headers.get("Content-Type", "")
                
                # Don't download huge files
                content_length = resp.headers.get("Content-Length")
                if content_length and int(content_length) > 10_000_000:  # 10MB
                    return None, ct, status
                
                raw = await resp.read()
                return raw, ct, status
                
        except asyncio.TimeoutError:
            if attempt < MAX_RETRIES:
                await asyncio.sleep(1.0 * (attempt + 1))
                continue
            return None, None, 0
            
        except Exception as e:
            if attempt < MAX_RETRIES:
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            return None, None, 0
    
    return None, None, 0

# -----------------------
# TEXT EXTRACTION
# -----------------------
def extract_text_from_html(html_bytes: bytes, url: str) -> Tuple[str, Dict[str, Any]]:
    """Extract clean text from HTML"""
    html = html_bytes.decode("utf-8", errors="ignore")
    meta = {"title": None, "lang": None}
    
    # Try trafilatura first (best results)
    if trafilatura:
        try:
            extracted = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=True,
                include_links=False
            )
            
            if extracted and len(extracted.strip()) > 100:
                # Get title separately
                soup = BeautifulSoup(html, "html.parser")
                if soup.title and soup.title.string:
                    meta["title"] = soup.title.string.strip()
                if soup.html:
                    meta["lang"] = soup.html.get("lang")
                
                return extracted, meta
        except Exception:
            pass
    
    # Fallback to readability
    if ReadabilityDocument:
        try:
            doc = ReadabilityDocument(html)
            content_html = doc.summary()
            title = doc.title()
            
            soup = BeautifulSoup(content_html, "html.parser")
            text = soup.get_text(separator="\n", strip=True)
            
            meta["title"] = title
            
            # Get lang from original HTML
            soup_full = BeautifulSoup(html, "html.parser")
            if soup_full.html:
                meta["lang"] = soup_full.html.get("lang")
            
            return text, meta
        except Exception:
            pass
    
    # Last resort: BeautifulSoup only
    soup = BeautifulSoup(html, "html.parser")
    
    # Remove unwanted elements
    for tag in soup(["script", "style", "noscript", "nav", "footer", "aside"]):
        tag.decompose()
    
    text = soup.get_text(separator="\n", strip=True)
    
    if soup.title and soup.title.string:
        meta["title"] = soup.title.string.strip()
    if soup.html:
        meta["lang"] = soup.html.get("lang")
    
    return text, meta

def extract_text_from_pdf(raw_bytes: bytes) -> Tuple[str, Dict[str, Any]]:
    """Extract text from PDF"""
    if not pdf_extract_text:
        return "", {}
    
    try:
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(raw_bytes)
            tmp_path = tmp.name
        
        text = pdf_extract_text(tmp_path)
        os.unlink(tmp_path)
        
        return text, {"title": None, "lang": None}
    except Exception:
        return "", {}

# -----------------------
# PAYWALL DETECTION
# -----------------------
def detect_paywall(text: str) -> bool:
    """Simple paywall detection"""
    if not text or len(text) < 200:
        return False
    
    text_lower = text.lower()
    
    # Check for paywall keywords
    keyword_count = sum(1 for kw in PAYWALL_KEYWORDS if kw in text_lower)
    
    # If multiple keywords found, likely paywall
    if keyword_count >= 2:
        return True
    
    # Check if text is suspiciously short
    if len(text.strip()) < 500 and "subscribe" in text_lower:
        return True
    
    return False

# -----------------------
# STORAGE
# -----------------------
async def save_raw(url: str, raw: bytes, content_type: str, status: int) -> str:
    """Save raw content"""
    fname = safe_filename(url)
    ext = ".pdf" if is_pdf_url(url, content_type) else ".html"
    path = os.path.join(RAW_STORAGE_DIR, fname + ext)
    
    async with aiofiles.open(path, "wb") as f:
        await f.write(raw or b"")
    
    # Save to DB
    async with db_lock:
        cur = DB.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO raw_pages (id, url, fetched_at, content_type, path, http_status) VALUES (?,?,?,?,?,?)",
            (fname, url, time.time(), content_type, path, status)
        )
        DB.commit()
    
    return path

async def save_cleaned(id_: str, url: str, meta: Dict[str, Any], text: str, summary: Optional[str] = None):
    """Save cleaned text"""
    fname = safe_filename(url) + ".txt"
    path = os.path.join(CLEAN_STORAGE_DIR, fname)
    
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(text)
    
    fp = fingerprint_text(text)
    word_count = len(text.split())
    
    async with db_lock:
        cur = DB.cursor()
        cur.execute(
            """INSERT OR REPLACE INTO cleaned_pages
            (id, url, title, text_path, summary, lang, fingerprint, word_count)
            VALUES (?,?,?,?,?,?,?,?)""",
            (id_, url, meta.get("title"), path, summary, meta.get("lang"), fp, word_count)
        )
        DB.commit()
    
    return path

# -----------------------
# MAIN SCRAPER
# -----------------------
async def scrape_single(session: aiohttp.ClientSession, task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Scrape a single URL
    
    task format:
    {
        "id": "u1",
        "url": "https://...",
        "sub_question": "q1",
        "meta": {...}
    }
    """
    url = task["url"]
    uid = task.get("id") or hashlib.sha1(url.encode()).hexdigest()[:12]
    
    result = {
        "id": uid,
        "url": url,
        "status": "failed",
        "notes": [],
        "clean_path": None,
        "raw_path": None
    }
    
    try:
        # Fetch
        raw, content_type, status = await fetch_url(session, url)
        
        if not raw:
            result["status"] = "fetch_failed"
            result["notes"].append(f"fetch_failed_status:{status}")
            return result
        
        # Save raw
        raw_path = await save_raw(url, raw, content_type or "", status)
        result["raw_path"] = raw_path
        
        # Extract text
        if is_pdf_url(url, content_type):
            text, meta = extract_text_from_pdf(raw)
        else:
            text, meta = extract_text_from_html(raw, url)
        
        # Check for paywall
        if detect_paywall(text):
            result["status"] = "paywall_detected"
            result["notes"].append("paywall heuristics")
            # Still save what we got
            if text:
                await save_cleaned(uid, url, meta, text)
            return result
        
        # Check if extraction succeeded
        if not text or len(text.strip()) < 100:
            result["status"] = "extraction_failed"
            result["notes"].append(f"text_too_short:{len(text)}")
            return result
        
        # Create summary
        summary = text[:400].strip().replace("\n", " ") + "..." if len(text) > 400 else text[:200]
        
        # Save cleaned
        clean_path = await save_cleaned(uid, url, meta, text, summary)
        
        result["clean_path"] = clean_path
        result["status"] = "ok"
        result["title"] = meta.get("title")
        result["lang"] = meta.get("lang")
        result["summary"] = summary
        result["fingerprint"] = fingerprint_text(text)
        
        return result
        
    except Exception as e:
        result["status"] = "error"
        result["notes"].append(str(e))
        return result

# -----------------------
# BATCH SCRAPER
# -----------------------
async def scrape_batch(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Scrape multiple URLs with concurrency control
    """
    ensure_dirs()
    
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT, limit_per_host=2)
    timeout = aiohttp.ClientTimeout(total=30, connect=10)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        results = []
        
        # Process with semaphore for rate limiting
        sem = asyncio.Semaphore(MAX_CONCURRENT)
        
        async def limited_scrape(task):
            async with sem:
                result = await scrape_single(session, task)
                # Small delay between requests
                await asyncio.sleep(DELAY_BETWEEN_REQUESTS)
                return result
        
        # Create all tasks
        scrape_tasks = [limited_scrape(task) for task in tasks]
        
        # Execute with progress
        print(f"Scraping {len(tasks)} URLs...")
        for i, coro in enumerate(asyncio.as_completed(scrape_tasks)):
            result = await coro
            results.append(result)
            
            # Progress
            if (i + 1) % 5 == 0 or (i + 1) == len(tasks):
                success_count = sum(1 for r in results if r["status"] == "ok")
                print(f"  Progress: {i+1}/{len(tasks)} | Success: {success_count}")
        
        return results

# -----------------------
# CLI
# -----------------------
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Ultra-Agent Scraper")
    parser.add_argument("--input", required=True, help="JSON file with tasks")
    parser.add_argument("--outdir", default="data", help="Output directory")
    args = parser.parse_args()
    
    # Update paths
    RAW_STORAGE_DIR = os.path.join(args.outdir, "raw")
    CLEAN_STORAGE_DIR = os.path.join(args.outdir, "clean")
    DB_FILE = os.path.join(args.outdir, "scraper.db")
    
    # Reinitialize DB with new path
    DB = init_db()
    
    # Load tasks
    with open(args.input, "r") as f:
        tasks = json.load(f)
    
    print(f"Loaded {len(tasks)} tasks from {args.input}")
    
    # Run scraper
    results = asyncio.run(scrape_batch(tasks))
    
    # Save results
    output_file = os.path.join(args.outdir, "scrape_results.json")
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    # Summary
    success = sum(1 for r in results if r["status"] == "ok")
    paywall = sum(1 for r in results if r["status"] == "paywall_detected")
    failed = len(results) - success - paywall
    
    print(f"\n{'='*60}")
    print(f"SCRAPING COMPLETE")
    print(f"{'='*60}")
    print(f"Total URLs: {len(results)}")
    print(f"Success: {success} ({success/len(results)*100:.1f}%)")
    print(f"Paywall: {paywall}")
    print(f"Failed: {failed}")
    print(f"\nResults saved to: {output_file}")