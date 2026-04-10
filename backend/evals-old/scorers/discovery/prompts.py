"""Prompt templates for discovery LLM-as-judge scorers."""

HELPFULNESS_PROMPT = """You are evaluating a restaurant discovery response.

User Query: {{input}}
Agent Response: {{output}}

Rate the helpfulness of this response on a scale of 0-1:
- 1.0: Clear, well-formatted list with all relevant details (names, cuisine, hours, location). Professional tone.
- 0.7: Helpful but missing minor details or could be clearer.
- 0.4: Somewhat helpful but confusing, incomplete, or poorly formatted.
- 0.0: Unhelpful, truncated, incoherent, or doesn't address the query.

Consider:
- Is the restaurant list easy to read and understand?
- Are restaurant names clearly stated?
- Are key details (cuisine, hours, location) included?
- Is the tone friendly and professional?
- Is the response well-structured?

Return ONLY a single number between 0 and 1 on the first line.
Then explain your reasoning.
"""

PROACTIVITY_PROMPT = """You are evaluating whether a restaurant discovery response is proactive and helpful.

User Query: {{input}}
Agent Response: {{output}}

Rate proactivity on a scale of 0-1:
- 1.0: Agent suggests alternatives (different times, cuisines, areas), asks clarifying questions, or offers next steps.
- 0.7: Agent addresses the query adequately but doesn't offer proactive help.
- 0.4: Agent responds minimally; missed opportunities to help.
- 0.0: Agent response doesn't acknowledge user needs or offer any guidance.

Consider:
- If the query was ambiguous, did the agent ask clarifying questions?
- If results were limited, did the agent suggest alternatives?
- Did the agent offer to help with next steps (filtering, booking, changing preferences)?
- Is the agent being helpful without being pushy?

Return ONLY a single number between 0 and 1 on the first line.
Then explain your reasoning.
"""
