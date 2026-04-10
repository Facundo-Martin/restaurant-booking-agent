# Discovery Scorers

Scorers for the Discovery feature evaluation.

## Scorers

- **rag_quality_scorer** (composite autoeval)
  - Returns: ContextRelevancy, Faithfulness, AnswerRelevancy
  - Cost: ~3 LLM calls

- **agent_helpfulness_scorer** (LLM-as-judge)
  - Evaluates: response clarity, completeness, format
  - Cost: 1 Bedrock call

- **agent_proactivity_scorer** (LLM-as-judge)
  - Evaluates: offers alternatives, clarifications, next steps
  - Cost: 1 Bedrock call

- **tool_routing_correctness** (custom code, in common/)
  - Evaluates: agent called retrieve tool
  - Cost: none (deterministic)

- **data_privacy_scorer** (custom code, in common/)
  - Evaluates: no PII leakage
  - Cost: none (regex patterns)
