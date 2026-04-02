from unittest.mock import MagicMock, patch

import pytest

from app.agent.prompts import SYSTEM_PROMPT


def _mock_prompt(content: str) -> MagicMock:
    prompt = MagicMock()
    prompt.build.return_value = {
        "messages": [{"role": "system", "content": content}],
    }
    return prompt


def test_load_system_prompt_falls_back_to_local_prompt_when_disabled():
    from app.agent.prompt_loader import load_system_prompt

    with (
        patch.dict("os.environ", {}, clear=False),
        patch("app.agent.prompt_loader.braintrust.load_prompt") as load_prompt,
    ):
        assert load_system_prompt() == SYSTEM_PROMPT

    load_prompt.assert_not_called()


def test_load_system_prompt_uses_braintrust_environment_when_set():
    from app.agent.prompt_loader import load_system_prompt

    with (
        patch.dict("os.environ", {"BRAINTRUST_PROMPT_ENVIRONMENT": "development"}),
        patch(
            "app.agent.prompt_loader.braintrust.load_prompt",
            return_value=_mock_prompt("managed prompt"),
        ) as load_prompt,
    ):
        assert load_system_prompt() == "managed prompt"

    assert load_prompt.call_args.kwargs["environment"] == "development"
    assert load_prompt.call_args.kwargs["version"] is None


def test_load_system_prompt_prefers_explicit_version_over_environment():
    from app.agent.prompt_loader import load_system_prompt

    with (
        patch.dict(
            "os.environ",
            {
                "BRAINTRUST_PROMPT_VERSION": "7",
                "BRAINTRUST_PROMPT_ENVIRONMENT": "production",
            },
        ),
        patch(
            "app.agent.prompt_loader.braintrust.load_prompt",
            return_value=_mock_prompt("managed prompt"),
        ) as load_prompt,
    ):
        assert load_system_prompt() == "managed prompt"

    assert load_prompt.call_args.kwargs["version"] == "7"
    assert load_prompt.call_args.kwargs["environment"] is None


def test_load_system_prompt_rejects_non_system_prompt_shapes():
    from app.agent.prompt_loader import load_system_prompt

    prompt = MagicMock()
    prompt.build.return_value = {
        "messages": [
            {"role": "system", "content": "a"},
            {"role": "user", "content": "b"},
        ],
    }

    with (
        patch.dict("os.environ", {"BRAINTRUST_PROMPT_ENVIRONMENT": "development"}),
        patch("app.agent.prompt_loader.braintrust.load_prompt", return_value=prompt),
    ):
        with pytest.raises(ValueError):
            load_system_prompt()
