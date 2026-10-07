# Agentic incident orchestrator

Local prototype. An incoming error is normalized, classified, deduplicated, queued, investigated with Claude and narrow tools, and written up as a Markdown report.

Scope and architecture constraints are in `PROJECT_CONTEXT_agentic_incident_orchestrator.md`. A picture of what runs today is in [docs/architecture.md](docs/architecture.md).

## Layout

A module stays directly under `agentsmith/` while it is one file the rest of the package imports. A folder starts when that concern becomes several modules. New code follows that split.

`main.py` is the command. It loads one incident file and calls `receive`.

Shared modules:

- `agentsmith/models.py` defines `IncidentInput`, `Incident`, and `InvestigationContext`, including the allowed categories and severities.
- `agentsmith/manager.py` normalizes an error, fingerprints it, and either opens an incident or counts a duplicate.
- `agentsmith/queue.py` is the only storage. Callers do not depend on SQLite.
- `agentsmith/pipeline.py` is the only sequencer. `receive` accepts and classifies an error into the queue. `process_next` pulls the highest-severity incident that has no conclusion yet, gathers evidence, and runs the investigation loop. One command processes one incident.

Folders:

- `agentsmith/steps/` is one module per pipeline stage. `classify.py` owns the `Classification` schema. `gather_evidence.py` calls the tools and does not call a model. `investigate.py` is the solving loop: the brain reads the evidence, may request one more tool, and stops with a cause and a proposed fix. `fix.py` turns that recommendation into a unified diff and does not edit a repo. `judge.py` is one pass over that diff. `accept` is required before `open_pr.py` submits it. A bad diff goes back to the fixer once. A diff that does not fix the bug goes back to the investigation once. Prompt text and the numeric limits live in `config/pipeline.toml`.
- `agentsmith/brains/` is the model boundary. Stages call a `Brain`. `ClaudeBrain` is the current implementation and runs as `sonnet` or `opus`.
- `agentsmith/adapters/` is the only place that contacts an external system. Logs, git, telemetry, and issues each get one module.

`agentsmith/tools.py` is the dispatcher stages call. The tools are `get_logs`, `get_machine_state`, `get_recent_changes`, `get_file`, `get_pull_request_diff`, and `open_pull_request`. `LOGS_ADAPTER`, `TELEMETRY_ADAPTER`, `GIT_ADAPTER`, and `GITHUB_ADAPTER` select the implementation. `fixture` is the default. `GITHUB_ADAPTER=mcp` calls the GitHub MCP server at `GITHUB_MCP_URL`. `LOGS_ADAPTER=mcp` calls `query_logs` on the GCP logs server at `LOGS_MCP_URL`. Both stay on `fixture` when those tunnels are down.

`report.py` is the placeholder for the Markdown report.

`samples/` holds the fixed errors used to run the command. The sample service name `video-indexer` comes from the project scenario. `config/service_map.json` maps it to the repo `lumana/video-indexer`. `fixtures/` holds the logs, machine snapshots, and commits the fixture adapters read. `data/incidents.sqlite` is created at runtime.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Put an Anthropic API key in `.env`. Brain, model (`sonnet` or `opus`), prompts, the investigation turn cap, the token limit, and the log window are in `config/pipeline.toml`. `BRAIN` and `CLAUDE_MODEL` in the environment override the file for one run. A stage can override those with `CLASSIFY_BRAIN` and `CLASSIFY_CLAUDE_MODEL`. `BRAIN_DEBUG=1` appends every prompt and response to `data/brain-debug.json`.

## Accept a sample incident

From the repo root, with the venv active:

```bash
python main.py samples/reconnect_crash_1.json
python main.py samples/reconnect_crash_2.json
python main.py samples/unrelated_error.json
```

Each command stores the error, then pulls the highest-severity incident that does not yet have a conclusion. That pulled incident is the one that gets evidence and the investigation loop. It may be an older incident, not the error in this file. A second command pulls the next one. Nothing keeps running after that. State is stored in `data/incidents.sqlite`. Delete that file to reset.
