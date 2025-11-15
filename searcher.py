import aiohttp
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import quote
import json
from typing import List, Dict, Optional
from planner import plan as plan_output
from dotenv import load_dotenv
import os

# ==========================
# CONFIG
# ==========================
load_dotenv()
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
TAVILY_URL = "https://api.tavily.com/search"

HEADERS = {
    "User-Agent": "ResearchAgent/1.0 (+https://example.com)"
}

# Domain quality lists
GOOD_DOMAINS = [
    "gov", "edu", "nber.org", "federalreserve.gov", "frbsf.org",
    "bea.gov", "imf.org", "worldbank.org", "brookings.edu",
    "reuters.com", "bloomberg.com", "economist.com", "census.gov",
    "bls.gov", "treasury.gov"
]

BAD_DOMAINS = [
    "quora", "reddit", "medium.com", "investopedia.com", 
    "forbes.com/sites", "answers.yahoo", "ehow.com"
]


# ==========================
# UTILITY FUNCTIONS
# ==========================
def domain_quality(url: str) -> float:
    """Score URL based on domain reputation"""
    url_lower = url.lower()
    
    for good in GOOD_DOMAINS:
        if good in url_lower:
            return 0.3
    
    for bad in BAD_DOMAINS:
        if bad in url_lower:
            return -0.2
    
    return 0.0


def relevance_score(query: str, title: str, snippet: str) -> float:
    """Calculate relevance score based on keyword matching"""
    query_words = set(query.lower().split())
    text = (title + " " + snippet).lower()
    
    match_count = sum(1 for word in query_words if word in text)
    match_ratio = match_count / max(len(query_words), 1)
    
    # Base score + bonus for matches
    return min(1.0, 0.4 + (match_ratio * 0.6))


# ==========================
# DUCKDUCKGO FALLBACK SEARCH
# ==========================
async def duckduckgo_search(session: aiohttp.ClientSession, query: str, max_results: int = 10) -> List[Dict]:
    """Fallback search using DuckDuckGo HTML"""
    try:
        encoded = quote(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        
        async with session.get(url, headers=HEADERS, timeout=10) as resp:
            if resp.status != 200:
                return []
            html = await resp.text()
        
        soup = BeautifulSoup(html, "html.parser")
        results = []
        
        # DuckDuckGo HTML structure
        for result_div in soup.select(".result")[:max_results]:
            link = result_div.select_one(".result__a")
            snippet_elem = result_div.select_one(".result__snippet")
            
            if not link:
                continue
            
            href = link.get("href", "")
            title = link.get_text(strip=True)
            snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
            
            # Clean up DuckDuckGo redirect URLs
            if href.startswith("//duckduckgo.com/l/?"):
                continue
            
            results.append({
                "url": href,
                "title": title,
                "snippet": snippet,
                "engine": "duckduckgo",
                "date": None
            })
        
        return results
    
    except Exception as e:
        print(f"DuckDuckGo search failed for '{query}': {e}")
        return []


# ==========================
# TAVILY PRIMARY SEARCH
# ==========================
async def tavily_search(session: aiohttp.ClientSession, query: str, max_results: int = 10) -> Optional[List[Dict]]:
    """Primary search using Tavily API"""
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "advanced",
        "max_results": max_results,
        "include_answer": False
    }
    
    try:
        async with session.post(TAVILY_URL, json=payload, headers=HEADERS, timeout=15) as resp:
            if resp.status != 200:
                print(f"Tavily API error: {resp.status}")
                return None
            
            data = await resp.json()
        
        results = []
        for item in data.get("results", []):
            results.append({
                "url": item.get("url", ""),
                "title": item.get("title", ""),
                "snippet": item.get("content", ""),
                "engine": "tavily",
                "date": item.get("published_date")
            })
        
        return results
    
    except Exception as e:
        print(f"Tavily search failed for '{query}': {e}")
        return None


# ==========================
# MAIN SEARCHER FUNCTION
# ==========================
async def run_searcher_for_subquestion(subq_id: str, subq_text: str, search_plan: Dict) -> Dict:
    """
    Execute searches for a single sub-question
    
    Args:
        subq_id: Sub-question identifier
        subq_text: The actual sub-question text (for better relevance scoring)
        search_plan: Search strategy from the plan
    
    Returns:
        Dictionary with search results
    """
    # Collect all queries
    queries = search_plan.get("queries", []).copy()
    
    # Add variants if available
    variants = search_plan.get("query_variants", {})
    for variant_type in ["academic", "general", "temporal"]:
        if variant_type in variants and variants[variant_type]:
            queries.append(variants[variant_type])
    
    # Deduplicate while preserving order
    queries = list(dict.fromkeys(queries))
    
    print(f"\n[{subq_id}] Executing {len(queries)} queries...")
    
    all_results = []
    queries_executed = []
    
    async with aiohttp.ClientSession() as session:
        for query in queries:
            print(f"  → Query: '{query}'")
            
            query_result = {
                "query": query,
                "source": None,
                "results_count": 0,
                "status": "failed"
            }
            
            # Try Tavily first
            tavily_results = await tavily_search(session, query, max_results=10)
            
            if tavily_results:
                all_results.extend(tavily_results)
                query_result["source"] = "tavily"
                query_result["results_count"] = len(tavily_results)
                query_result["status"] = "success"
                print(f"    ✓ Tavily: {len(tavily_results)} results")
            else:
                # Fallback to DuckDuckGo
                ddg_results = await duckduckgo_search(session, query, max_results=10)
                all_results.extend(ddg_results)
                query_result["source"] = "duckduckgo"
                query_result["results_count"] = len(ddg_results)
                query_result["status"] = "success" if ddg_results else "failed"
                print(f"    ⚠ DuckDuckGo fallback: {len(ddg_results)} results")
            
            queries_executed.append(query_result)
            
            # Small delay to be respectful
            await asyncio.sleep(0.5)
    
    # Deduplicate by URL
    seen_urls = set()
    unique_results = []
    
    for result in all_results:
        url = result["url"]
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_results.append(result)
    
    print(f"  → Total unique results: {len(unique_results)}")
    
    # Score and rank results
    # Use the sub-question text for relevance scoring
    scored_results = []
    
    for result in unique_results:
        # Calculate relevance against sub-question
        rel_score = relevance_score(
            subq_text,
            result["title"],
            result["snippet"]
        )
        
        # Add domain quality bonus
        dom_score = domain_quality(result["url"])
        
        # Final score
        final_score = rel_score + dom_score
        
        result["relevance_score"] = rel_score
        result["domain_score"] = dom_score
        result["rank_score"] = final_score
        
        scored_results.append(result)
    
    # Sort by rank score
    scored_results.sort(key=lambda x: x["rank_score"], reverse=True)
    
    # Take top 10
    top_results = scored_results[:10]
    
    return {
        "sub_question_id": subq_id,
        "sub_question_text": subq_text,
        "queries_executed": queries_executed,
        "total_results_found": len(unique_results),
        "results": top_results,
        "status": "complete"
    }


# ==========================
# RUN MULTIPLE SUB-QUESTIONS
# ==========================
async def run_searcher_for_all(subquestions: List[Dict]) -> List[Dict]:
    """
    Execute searches for all sub-questions in parallel
    
    Args:
        subquestions: List of sub-question dictionaries from the plan
    
    Returns:
        List of search results for each sub-question
    """
    tasks = []
    
    for subq in subquestions:
        subq_id = subq["id"]
        subq_text = subq["question"]
        search_plan = subq["search_strategy"]
        
        task = run_searcher_for_subquestion(subq_id, subq_text, search_plan)
        tasks.append(task)
    
    # Execute all in parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Handle any exceptions
    final_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"Error in sub-question {subquestions[i]['id']}: {result}")
            final_results.append({
                "sub_question_id": subquestions[i]["id"],
                "status": "error",
                "error": str(result)
            })
        else:
            final_results.append(result)
    
    return final_results


# ==========================
# DEMO USAGE
# ==========================
def clean_llm_json(llm_output: str) -> dict:
    """
    Clean LLM output that might have markdown code fences
    
    Handles formats like:
    ```json
    {...}
    ```
    
    Or just plain JSON
    """
    cleaned = llm_output.strip()
    
    # Remove markdown code fences
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]  # Remove ```json
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]   # Remove ```
    
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]  # Remove trailing ```
    
    # Strip again after removing fences
    cleaned = cleaned.strip()
    
    # Parse JSON
    return json.loads(cleaned)


async def main():
    """Demo showing how to use the searcher with your plan"""
    
    # Clean and parse the LLM output
    plan = clean_llm_json(plan_output)
    
    print("✓ Plan loaded and parsed successfully")
    print(f"  Found {len(plan['sub_questions'])} sub-questions")
    
    # Run searcher for all sub-questions
    print("\nStarting searcher...")
    results = await run_searcher_for_all(plan["sub_questions"])
    
    # Print results
    print("\n" + "="*60)
    print("SEARCH RESULTS")
    print("="*60)
    print(json.dumps(results, indent=2))
    
    # Save to file
    with open("search_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print("\n✓ Results saved to search_results.json")


if __name__ == "__main__":
    asyncio.run(main())
