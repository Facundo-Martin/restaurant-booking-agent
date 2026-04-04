"""Custom code scorer: tool routing correctness."""

from braintrust import Score


def tool_routing_correctness(
    output: str, trace: dict, expected_tool: str = "retrieve", **kwargs
) -> Score:
    """
    Check: Did agent call the expected tool?

    Args:
        output: Agent response (not used)
        trace: Trace dict with tool_calls list
        expected_tool: Name of tool that should be called

    Returns:
        Score: 1.0 if correct tool called, 0.0 otherwise
    """
    # Implementation in Phase 3
    pass


__all__ = ["tool_routing_correctness"]
