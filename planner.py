from google import genai

# -------------------------------
# CONFIG
# -------------------------------
API_KEY = "AIzaSyCioZspKL8LBOl-lWF9oK2NkfvW_ibMoU0"
MODEL_NAME = "gemini-2.5-flash"

query = "What is the reason of US recession"


# -------------------------------
# INIT MODEL CLIENT
# -------------------------------
def init_client(api_key: str):
    try:
        return genai.Client(api_key=api_key)
    except Exception as e:
        print("Error: Invalid API key.")
        print(str(e))
        exit()


client = init_client(API_KEY)


# -------------------------------
# PROMPT HELPERS
# -------------------------------

def build_analysis_prompt(query: str) -> str:
    return f"""
You are a query analysis system. Your job is to extract structured information from user research queries.

Analyze the following user query and extract key parameters. Be precise and objective.

USER QUERY: {query}

Respond ONLY with valid JSON:

{{
  "primary_intent": "<information_seeking | causal_analysis | comparison | how_to | trend_analysis | definition | data_request | solution_seeking>",
  
  "scope": {{
    "breadth": "<broad_overview | focused_aspect | deep_dive>",
    "depth_level": "<introductory | intermediate | expert>",
    "specificity_score": "<1-5>"
  }},
  
  "domains": ["<list domains>"],
  
  "constraints": {{
    "temporal": {{
      "has_constraint": <true|false>,
      "type": "<historical | current | future | specific_period | null>",
      "details": "<string or null>"
    }},
    "geographic": {{
      "has_constraint": <true|false>,
      "locations": ["<list or empty>"]
    }},
    "domain_specific": ["<list or empty>"]
  }},
  
  "implicit_requirements": {{
    "needs_data": <true|false>,
    "needs_mechanisms": <true|false>,
    "needs_examples": <true|false>,
    "needs_comparisons": <true|false>,
    "needs_step_by_step": <true|false>,
    "needs_recommendations": <true|false>
  }},
  
  "entities": {{
    "primary_entities": ["<list>"],
    "secondary_entities": ["<list>"]
  }},
  
  "ambiguities": ["<list>"],
  
  "complexity_score": "<1-5>"
}}
"""


def build_planning_prompt(query: str, analysis_json: str) -> str:
    return f"""
You are a research planning system. Create an actionable research plan.

USER QUERY: {query}

QUERY ANALYSIS:
{analysis_json}

Output ONLY valid JSON:

{{
  "research_strategy": {{
    "approach": "<sequential_deep_dive | parallel_broad_search | hierarchical_breakdown | comparative_analysis>",
    "estimated_complexity": "<low | medium | high>",
    "estimated_search_count": <3-15>
  }},
  
  "sub_questions": [
    {{
      "id": "q1",
      "question": "<sub-question>",
      "rationale": "<why needed>",
      "priority": "<critical | high | medium | low>",
      "dependencies": [],
      
      "search_strategy": {{
        "queries": [
          "<query 1>",
          "<query 2>",
          "<query 3>"
        ],
        "query_variants": {{
          "academic": "<academic phrasing>",
          "general": "<simple phrasing>",
          "temporal": "<time-specific phrasing>"
        }},
        "preferred_source_types": ["<list>"],
        "date_filter": "<recent_only | last_year | last_5_years | no_filter | specific_period>",
        "geographic_filter": "<region or global>"
      }},
      
      "expected_information": {{
        "type": ["<definitions | mechanisms | data | examples | comparisons>"],
        "completeness_criteria": "<how to know it's complete>",
        "minimum_sources": <number>
      }}
    }}
  ],
  
  "execution_plan": {{
    "phase_1": {{
      "description": "Foundation gathering",
      "questions": ["q1"],
      "can_parallelize": false
    }},
    "phase_2": {{
      "description": "Deep dive",
      "questions": ["q2", "q3"],
      "can_parallelize": true
    }},
    "phase_3": {{
      "description": "Verification and synthesis",
      "questions": ["q4"],
      "can_parallelize": true
    }}
  }},
  
  "success_criteria": {{
    "minimum_requirements": ["<list>"],
    "quality_indicators": ["<list>"],
    "stopping_conditions": "<condition>"
  }},
  
  "synthesis_guidance": {{
    "final_answer_structure": "<structure>",
    "key_points_to_address": ["<list>"],
    "caveats_to_include": ["<list>"]
  }}
}}
"""


# -------------------------------
# MODEL CALLING FUNCTION
# -------------------------------
def run_model(prompt: str):
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )
        return response.text
    except Exception as e:
        print(f"Model error: {e}")
        return None


# -------------------------------
# MAIN EXECUTION
# -------------------------------

# Step 1: Analyze Query
analysis_prompt = build_analysis_prompt(query)
analysis_result = run_model(analysis_prompt)

if not analysis_result:
    print("Failed to generate analysis.")
    exit()

# Step 2: Create Research Plan
planning_prompt = build_planning_prompt(query, analysis_result)
plan = run_model(planning_prompt)

# Output
print("===== QUERY ANALYSIS =====")
print(analysis_result)

print("\n===== RESEARCH PLAN =====")
print(plan)
