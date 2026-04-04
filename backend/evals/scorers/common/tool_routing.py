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
    tool_calls = trace.get("tool_calls", [])

    # Check if expected tool was called
    called_tools = [call.get("name") for call in tool_calls]
    tool_called = expected_tool in called_tools

    return Score(
        name="Tool Routing",
        score=1.0 if tool_called else 0.0,
        metadata={
            "expected_tool": expected_tool,
            "tools_called": called_tools,
        },
    )


__all__ = ["tool_routing_correctness"]
