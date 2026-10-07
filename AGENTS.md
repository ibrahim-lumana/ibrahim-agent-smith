# Agent instructions

Read `PROJECT_CONTEXT_agentic_incident_orchestrator.md` before changing this project. It is the source of truth for scope. This file is the current approach.

## What this is

A local prototype of an incident-investigation orchestrator. An external trigger already detected the error. This system normalizes it, classifies it, deduplicates it, queues it, gathers evidence, and runs a reasoning loop until it writes a root-cause hypothesis and a proposed fix. `fix` turns that into a unified diff. `judge` checks the diff. On accept, `open_pr` submits it through `open_pull_request`.

The prototype does not edit a checkout and does not merge. The Markdown report is not built yet. One investigation runs at a time. Development runs on this machine.

`samples/reconnect_crash_1.json` is a fictional `video-indexer` crash used to test the loop. It is not a real service, and nothing here connects to an edge device.

## What is deterministic, and what calls a model

Fingerprint, dedup, queue order, service-to-repo mapping, and evidence gathering are ordinary code. Evidence gathering reads logs for the window in `config/pipeline.toml`, one machine snapshot, and recent commits. It does not call a model.

A model is used for four stages. Classification runs only for a new incident and sets category, severity, and suspected component. The investigation loop then reads that evidence. Each turn it asks for one tool or writes the cause, confidence, and proposed fix. The tool call is still ordinary code. The turn cap is `max_iterations` in `config/pipeline.toml`. After a conclusion, `fix` makes one model call and returns a unified diff. It sees the recommendation and the file text already collected. It does not get a shell, does not edit a checkout, and does not open a pull request. `judge` then reads that diff once and checks that the change is safe, that it matches the recommendation, and that it fixes the bug. Only `accept` may continue. A bad diff goes back to `fix` once. A diff that does not fix the bug goes back to the investigation once. A second failure stops and is stored. `max_revisions` in `config/pipeline.toml` is that cap. After `accept`, `open_pr` calls `open_pull_request` with the title, body, and diff. The fixture tool returns a local `fixture://` URL and does not contact GitHub. `GITHUB_ADAPTER=mcp` calls a tool of that same name and expects JSON with `number` and `html_url`. His current server does not implement that write.

One command stores the error from the file you pass, then investigates the highest-severity incident that has no conclusion yet. That may be an older incident.

## Relation to `third_party/agentic-dev`

That directory is a local clone of the manager's platform, `lumanaai/agentic-dev`, and is gitignored. It is not part of this repo. He runs it on one VM with Docker Compose, the Claude Agent SDK, Redis, and Postgres. His agents edit code inside a worktree. We do not move this orchestrator onto that platform, and we do not start his ingress, scheduler, workers, Redis, or Postgres.

We keep this pipeline and call his tools. The tool servers this loop uses are GitHub (`tools/mcp-servers/github`) and GCP logs (`tools/mcp-servers/gcp`). His GitHub server is read-only and only answers for repos listed in his `config/repos.yaml` (`lumanaai/analytics`, `lumanaai/edge`, `lumanaai/lumix-cloud`). `query_logs` reads Cloud Logging in the projects listed in his `config/mcp-servers.yaml`. Machine state and recent commits stay on fixture adapters. Do not treat loose commits as how this company ships. Production changes are merged pull requests.

`get_file` and `get_pull_request_diff` go to the GitHub server when `GITHUB_ADAPTER=mcp`. `get_logs` calls `query_logs` when `LOGS_ADAPTER=mcp`. Neither container publishes a port. Each listens on the VM's Docker network. From this machine, forward each container with SSH and point `LOGS_MCP_URL` and `GITHUB_MCP_URL` at the local ends of those tunnels. The current login is `ibrahimjub@192.168.100.65`, and his checkout on that machine is `/agentic-dev`. The GitHub App private key and the GCP service-account key stay on the VM in `/etc/agentic/secrets`. Do not copy them into this repo. This project does not need to run on that VM.

## Config

`config/pipeline.toml` holds the brain, the model (`sonnet` or `opus`), the stage prompts, the turn cap, the revision cap, the token limit, and the log window. A `model` line under `[classify]`, `[investigate]`, `[fix]`, or `[judge]` overrides `[brain]` for that stage only.

`.env` holds `ANTHROPIC_API_KEY`, the adapter switches, and `BRAIN_DEBUG`. `BRAIN` and `CLAUDE_MODEL`, if set, override the toml for one run. A stage override uses `<TASK>_BRAIN` and `<TASK>_CLAUDE_MODEL`. `BRAIN_DEBUG=1` appends every prompt and response to `data/brain-debug.json`.

Fixture is the default for every adapter. `fixture` must keep working when his server is down.

## Do not build yet

Kubernetes, distributed workers, parallel investigations, autoscaling, automatic deployment, automatic merge, a UI, a vector database, or a multi-agent platform.

Do not put secrets in source files. API keys belong in `.env`, which is gitignored. `.env.example` lists the variable names.
