"""Smoke tests — extend with behaviour-driven tests per feature work."""


def test_package_version() -> None:
    import gestalt

    assert gestalt.__version__ == "0.1.0"


def test_crew_class_exists() -> None:
    """Building `GestaltCrew()` touches the LLM stack; smoke-test the symbol only."""
    from gestalt.crew import GestaltCrew

    assert GestaltCrew.__name__ == "GestaltCrew"


def test_custom_tool_placeholder() -> None:
    from gestalt.tools.custom_tool import CustomTool

    assert "placeholder" in CustomTool()._run("hello").lower()
