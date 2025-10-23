# Copilot Agent Guidelines — Usage & Change Requests

This repository includes an operational policy for the Copilot Agent located at `docs/airflow_copilot_agent_guidelines.md`.

How the agent will behave:
- The agent will follow the rules in `airflow_copilot_agent_guidelines.md` for any changes related to Apache Airflow.
- The agent must verify code references in `/dags`, `/plugins`, and `/config` before proposing edits.

Requesting changes to the guidelines:
- Open an issue or submit a PR changing `docs/airflow_copilot_agent_guidelines.md`.
- The agent will ask clarifying questions if a requested change introduces ambiguity.

Optional follow-ups (not implemented automatically):
- Add a pre-commit hook that reminds contributors to confirm changes against the guidelines.
- Add a CI check that validates the agent's edits reference existing files and that DAGs parse with `airflow dags test`.

⚠️ Note: The agent will not change this file without explicit user approval.
