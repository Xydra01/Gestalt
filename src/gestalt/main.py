"""Entry point for the Gestalt crew."""

from gestalt.crew import GestaltCrew


def run() -> None:
    inputs = {"topic": "AI agent guardrails"}
    GestaltCrew().crew().kickoff(inputs=inputs)


if __name__ == "__main__":
    run()
