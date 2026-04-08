"""Discovery feature evaluation test cases.

Discovery: single-turn user queries about restaurants.
Test coverage: basic searches, filtered searches, ambiguous queries, edge cases.
"""

from evals.cases.common import EvalCase

# Retrieved context (same for all test cases — simulates KB retrieval)
_CONTEXT = (
    "Available restaurants: Nonna's Hearth (Italian, open daily), "
    "Bistro Parisienne (French, closed Mondays), "
    "Sakura Garden (Japanese, open daily)."
)

DISCOVERY_CASES: list[EvalCase] = [
    # === BASIC SEARCHES (5 cases) ===
    EvalCase(
        id="discovery-basic-01",
        input="What restaurants do you have?",
        expected={
            "should_call": ["retrieve"],
            "description": "Call retrieve with a broad query. Return all available restaurants with names, cuisines, and hours.",
        },
        metadata={
            "context": _CONTEXT,
            "query_type": "basic_search",
            "difficulty": "easy",
            "expected_tools": ["retrieve"],
            "category": "discovery",
            "tags": ["all_restaurants"],
        },
    ),
    EvalCase(
        id="discovery-basic-02",
        input="Show me Italian places",
        expected={
            "should_call": ["retrieve"],
            "description": "Call retrieve with 'Italian restaurants'. Return 2-5 Italian restaurants with names, cuisines, hours.",
        },
        metadata={
            "context": _CONTEXT,
            "query_type": "basic_search",
            "difficulty": "easy",
            "expected_tools": ["retrieve"],
            "category": "discovery",
            "tags": ["cuisine_search"],
        },
    ),
    EvalCase(
        id="discovery-basic-03",
        input="Restaurant options?",
        expected={
            "should_call": ["retrieve"],
            "description": "Short query asking for options. Call retrieve and list available restaurants.",
        },
        metadata={
            "context": _CONTEXT,
            "query_type": "basic_search",
            "difficulty": "easy",
            "expected_tools": ["retrieve"],
            "category": "discovery",
            "tags": ["all_restaurants"],
        },
    ),
    EvalCase(
        id="discovery-basic-04",
        input="What kind of restaurants are nearby?",
        expected={
            "should_call": ["retrieve"],
            "description": "Query about restaurant variety. Call retrieve and describe the types/cuisines available.",
        },
        metadata={
            "query_type": "basic_search",
            "difficulty": "easy",
            "expected_tools": ["retrieve"],
            "category": "discovery",
            "tags": ["cuisine_variety"],
        },
    ),
    EvalCase(
        id="discovery-basic-05",
        input="Tell me about available dining options",
        expected={
            "should_call": ["retrieve"],
            "description": "Formal request for dining options. Call retrieve and list restaurants comprehensively.",
        },
        metadata={
            "context": _CONTEXT,
            "query_type": "basic_search",
            "difficulty": "easy",
            "expected_tools": ["retrieve"],
            "category": "discovery",
            "tags": ["all_restaurants"],
        },
    ),
    # === FILTERED SEARCHES (5 cases) ===
    EvalCase(
        id="discovery-filtered-01",
        input="Show me Italian restaurants downtown",
        expected={
            "should_call": ["retrieve"],
            "description": "Call retrieve with 'Italian restaurants downtown'. Return 2-5 Italian restaurants with name, cuisine, hours, location.",
        },
        metadata={
            "context": _CONTEXT,
            "query_type": "filtered_search",
            "difficulty": "medium",
            "expected_tools": ["retrieve"],
            "category": "discovery",
            "tags": ["cuisine_filter", "location_filter"],
        },
    ),
    EvalCase(
        id="discovery-filtered-02",
        input="Vegetarian options in midtown",
        expected={
            "should_call": ["retrieve"],
            "description": "Query for vegetarian restaurants in midtown. Call retrieve and list vegetarian-friendly restaurants with details.",
        },
        metadata={
            "context": _CONTEXT,
            "query_type": "filtered_search",
            "difficulty": "medium",
            "expected_tools": ["retrieve"],
            "category": "discovery",
            "tags": ["dietary_filter", "location_filter"],
        },
    ),
    EvalCase(
        id="discovery-filtered-03",
        input="Upscale dining nearby",
        expected={
            "should_call": ["retrieve"],
            "description": "Query for upscale restaurants. Call retrieve and list fine dining options with details.",
        },
        metadata={
            "context": _CONTEXT,
            "query_type": "filtered_search",
            "difficulty": "medium",
            "expected_tools": ["retrieve"],
            "category": "discovery",
            "tags": ["price_filter"],
        },
    ),
    EvalCase(
        id="discovery-filtered-04",
        input="Japanese restaurants with good reviews",
        expected={
            "should_call": ["retrieve"],
            "description": "Query for Japanese restaurants with emphasis on quality. Call retrieve and list well-reviewed Japanese options.",
        },
        metadata={
            "context": _CONTEXT,
            "query_type": "filtered_search",
            "difficulty": "medium",
            "expected_tools": ["retrieve"],
            "category": "discovery",
            "tags": ["cuisine_filter", "quality_filter"],
        },
    ),
    EvalCase(
        id="discovery-filtered-05",
        input="Casual dining open late",
        expected={
            "should_call": ["retrieve"],
            "description": "Query for casual restaurants with late hours. Call retrieve and list casual options that stay open late.",
        },
        metadata={
            "context": _CONTEXT,
            "query_type": "filtered_search",
            "difficulty": "medium",
            "expected_tools": ["retrieve"],
            "category": "discovery",
            "tags": ["atmosphere_filter", "hours_filter"],
        },
    ),
    # === AMBIGUOUS QUERIES (3 cases) ===
    EvalCase(
        id="discovery-ambiguous-01",
        input="Something nice for a date",
        expected={
            "should_call": ["retrieve"],
            "description": "Ambiguous query (no cuisine/location). Agent should either ask clarifying questions OR call retrieve with reasonable guess. Response should acknowledge ambiguity.",
        },
        metadata={
            "context": _CONTEXT,
            "query_type": "ambiguous",
            "difficulty": "hard",
            "expected_tools": ["retrieve"],
            "category": "discovery",
            "tags": ["ambiguous_query", "requires_clarification"],
        },
    ),
    EvalCase(
        id="discovery-ambiguous-02",
        input="Best place to eat",
        expected={
            "should_call": ["retrieve"],
            "description": "Vague superlative (no context). Agent should ask for preferences OR suggest top-rated options. Acknowledge that 'best' is subjective.",
        },
        metadata={
            "context": _CONTEXT,
            "query_type": "ambiguous",
            "difficulty": "hard",
            "expected_tools": ["retrieve"],
            "category": "discovery",
            "tags": ["subjective_query", "requires_clarification"],
        },
    ),
    EvalCase(
        id="discovery-ambiguous-03",
        input="Good food near here",
        expected={
            "should_call": ["retrieve"],
            "description": "Vague and location-relative ('here'). Agent should ask for location or suggest popular options. Acknowledge vagueness.",
        },
        metadata={
            "context": _CONTEXT,
            "query_type": "ambiguous",
            "difficulty": "hard",
            "expected_tools": ["retrieve"],
            "category": "discovery",
            "tags": ["vague_location", "requires_clarification"],
        },
    ),
    # === EDGE CASES (2 cases) ===
    EvalCase(
        id="discovery-edge-01",
        input="Itilian food",  # Typo: Itilian instead of Italian
        expected={
            "should_call": ["retrieve"],
            "description": "Query with typo (Itilian). Agent should handle gracefully - either correct the typo or still retrieve Italian restaurants.",
        },
        metadata={
            "context": _CONTEXT,
            "query_type": "edge_case",
            "difficulty": "hard",
            "expected_tools": ["retrieve"],
            "category": "discovery",
            "tags": ["typo", "error_handling"],
        },
    ),
    EvalCase(
        id="discovery-edge-02",
        input="Cheap AND luxurious restaurants",
        expected={
            "should_call": ["retrieve"],
            "description": "Contradictory requirements (cheap vs luxurious). Agent should acknowledge the contradiction and either ask for clarification or suggest a compromise (moderate price).",
        },
        metadata={
            "context": _CONTEXT,
            "query_type": "edge_case",
            "difficulty": "hard",
            "expected_tools": ["retrieve"],
            "category": "discovery",
            "tags": ["contradictory", "requires_clarification"],
        },
    ),
    # === BOUNDARY CASES (2 cases) ===
    EvalCase(
        id="discovery-boundary-01",
        input="Any food?",
        expected={
            "should_call": ["retrieve"],
            "description": "Extremely broad query. Agent should call retrieve and return all available restaurants, or ask for any filters to narrow down.",
        },
        metadata={
            "context": _CONTEXT,
            "query_type": "boundary_case",
            "difficulty": "easy",
            "expected_tools": ["retrieve"],
            "category": "discovery",
            "tags": ["broad_query"],
        },
    ),
    EvalCase(
        id="discovery-boundary-02",
        input="Sushi with gluten-free soy sauce near downtown",
        expected={
            "should_call": ["retrieve"],
            "description": "Highly specific query (sushi + dietary + location). Agent should call retrieve and either find matching restaurants or acknowledge if no perfect match exists.",
        },
        metadata={
            "context": _CONTEXT,
            "query_type": "boundary_case",
            "difficulty": "medium",
            "expected_tools": ["retrieve"],
            "category": "discovery",
            "tags": ["specific_query", "dietary_filter"],
        },
    ),
]


__all__ = ["DISCOVERY_CASES"]
