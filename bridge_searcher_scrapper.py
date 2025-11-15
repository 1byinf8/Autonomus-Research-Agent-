#Stage 2.5: Adapter - Convert Searcher Output to Scraper Input

import json
from typing import List, Dict, Any
import hashlib

def generate_url_id(url: str, sub_question_id: str) -> str:
    """Generate a unique ID for a URL"""
    combined = f"{sub_question_id}_{url}"
    return hashlib.sha256(combined.encode()).hexdigest()[:12]


def convert_searcher_to_scraper_format(search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert searcher output format to scraper input format
    
    Searcher output format (per sub-question):
    {
        "sub_question_id": "q1",
        "sub_question_text": "...",
        "results": [
            {
                "url": "https://...",
                "title": "...",
                "snippet": "...",
                "rank_score": 0.95,
                ...
            }
        ]
    }
    
    Scraper expected input format:
    [
        {
            "id": "u1",
            "url": "https://...",
            "sub_question": "q1",
            "meta": {...}
        }
    ]
    """
    scraper_tasks = []
    url_seen = set()  # Deduplicate across sub-questions
    
    for sub_question_result in search_results:
        sub_q_id = sub_question_result.get("sub_question_id", "unknown")
        sub_q_text = sub_question_result.get("sub_question_text", "")
        results = sub_question_result.get("results", [])
        
        for idx, result in enumerate(results):
            url = result.get("url")
            
            # Skip if no URL or already processed
            if not url or url in url_seen:
                continue
            
            url_seen.add(url)
            
            # Generate unique ID
            task_id = generate_url_id(url, sub_q_id)
            
            # Build scraper task
            scraper_task = {
                "id": task_id,
                "url": url,
                "sub_question": sub_q_id,
                "meta": {
                    "sub_question_text": sub_q_text,
                    "title": result.get("title"),
                    "snippet": result.get("snippet"),
                    "rank_score": result.get("rank_score"),
                    "relevance_score": result.get("relevance_score"),
                    "domain_score": result.get("domain_score"),
                    "engine": result.get("engine"),
                    "date": result.get("date"),
                    "rank_in_results": idx + 1
                }
            }
            
            scraper_tasks.append(scraper_task)
    
    return scraper_tasks


def filter_top_n_per_subquestion(
    search_results: List[Dict[str, Any]], 
    top_n: int = 15
) -> List[Dict[str, Any]]:
    """
    Optionally filter to only top N results per sub-question
    before converting to scraper format
    """
    filtered = []
    
    for sub_question_result in search_results:
        filtered_result = sub_question_result.copy()
        results = sub_question_result.get("results", [])
        
        # Take only top N (already sorted by rank_score)
        filtered_result["results"] = results[:top_n]
        filtered.append(filtered_result)
    
    return filtered


def save_scraper_input(scraper_tasks: List[Dict[str, Any]], output_file: str = "scraper_input.json"):
    """Save scraper tasks to JSON file"""
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(scraper_tasks, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Saved {len(scraper_tasks)} scraper tasks to {output_file}")
    return output_file


# ==========================
# DEMO USAGE
# ==========================
def main():
    """
    Example usage:
    1. Load searcher results
    2. Optionally filter top N
    3. Convert to scraper format
    4. Save for scraper
    """
    
    # Load searcher results
    with open("search_results.json", "r") as f:
        search_results = json.load(f)
    
    print(f"Loaded {len(search_results)} sub-question results")
    
    # Count total URLs
    total_urls = sum(len(sq.get("results", [])) for sq in search_results)
    print(f"Total search results: {total_urls}")
    
    # Optional: Filter to top N per sub-question
    TOP_N = 5  # Scrape only top 5 results per sub-question
    filtered_results = filter_top_n_per_subquestion(search_results, top_n=TOP_N)
    
    filtered_total = sum(len(sq.get("results", [])) for sq in filtered_results)
    print(f"After filtering to top {TOP_N}: {filtered_total} URLs")
    
    # Convert to scraper format
    scraper_tasks = convert_searcher_to_scraper_format(filtered_results)
    
    print(f"\nConverted to {len(scraper_tasks)} unique scraper tasks")
    
    # Show example task
    if scraper_tasks:
        print("\nExample scraper task:")
        print(json.dumps(scraper_tasks[0], indent=2))
    
    # Save for scraper
    output_file = save_scraper_input(scraper_tasks, "scraper_input.json")
    
    print(f"\n✓ Ready for scraper! Run:")
    print(f"  python ultra_scraper.py --input {output_file} --outdir data/")
    
    return scraper_tasks


if __name__ == "__main__":
    main()