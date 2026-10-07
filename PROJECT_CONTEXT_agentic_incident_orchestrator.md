# Project Context: Local Agentic Incident Investigation Orchestrator

## Goal

Build a small prototype of an agentic incident-investigation orchestrator.

The system receives an already-triggered production/log error, investigates it using a mix of deterministic logic + Claude API reasoning, gathers relevant information from external systems through isolated tool/MCP interfaces, and produces a structured investigation report with a root-cause hypothesis and proposed fix.

This is NOT yet a production-grade autonomous coding system.

The prototype should prove:

> Given an error, can we automatically gather useful evidence, reason over it, and produce a useful investigation + proposed fix for an engineer?

---

# Scope

The system should roughly perform:

Error input  
→ normalize  
→ classify  
→ deduplicate  
→ assign severity / priority  
→ enqueue  
→ process highest-priority incident  
→ gather evidence  
→ investigate iteratively using Claude  
→ form root-cause hypothesis  
→ propose fix  
→ generate investigation report

The trigger itself is OUT OF SCOPE.

Assume another component calls this system whenever a relevant error occurs.

---

# Important Constraints

This is an initial prototype.

DO NOT optimize for:

- scalability
- Kubernetes
- distributed workers
- parallel execution
- load balancing
- autoscaling
- complex retry infrastructure
- high availability

Only one investigation needs to run at a time.

Development should initially run locally.

External systems may initially be mocked/stubbed.

Claude API is available and will be the main reasoning engine.

Security boundaries are important architecturally even if implementations are initially fake.

---

# Architectural Principle: Isolate External Access

The orchestrator should NOT directly contain GCP, GitHub, Jira, machine telemetry, etc. implementation logic.

All external access should be exposed through narrow interfaces/tools.

Conceptually:

```text
Orchestrator
├── Logs MCP / Logs Tool
├── Git MCP / Git Tool
├── Machine/Telemetry MCP
├── Issue Tracker MCP
└── potentially other tools later
```

The important principle is:

> The agent may request information, but actual access to external systems happens through controlled tool interfaces.

This will later allow each tool to use a narrowly scoped service account / credential.

Examples:

Logs tool:
- read-only GCP logging permission

GitHub tool:
- initially read-only repository access
- later potentially branch/PR write permission

Machine telemetry:
- read-only telemetry

Production:
- no unrestricted credentials

For the prototype, tools may simply return local test fixtures.

---

# Input Contract

Assume the trigger gives us something approximately like:

```python
IncidentInput:
    error_id
    timestamp
    service
    component              # optional
    machine_id             # optional
    environment
    error_message
    stack_trace            # optional
    metadata               # arbitrary extra metadata
```

The orchestrator should depend only on this contract, not on how the incident was triggered.

We should be able to run something like:

```bash
python main.py sample_incident.json
```

for local testing.

---

# Main Components

## 1. Incident Manager

Responsibilities:

- normalize incoming incident
- classify incident
- create/update fingerprint
- deduplicate
- assign initial severity
- decide whether investigation is required
- enqueue incident

Possible classification:

```text
application_bug
infrastructure
network
configuration
dependency
unknown
```

Possible severity:

```text
critical
high
medium
low
```

Initial severity determines queue priority.

Severity may be revised after investigation.

---

## 2. Deduplication

Start simple and deterministic.

Possible fingerprint inputs:

```text
service
exception/error type
normalized error message
top stack frames
```

For example:

```python
fingerprint = hash(
    service +
    normalized_error +
    relevant_stack_frames
)
```

If an existing open incident has the same fingerprint:

- increment occurrence count
- update last_seen
- attach another sample
- DO NOT create another investigation

Later this may become smarter using embeddings/LLMs, but not initially.

---

## 3. Incident Queue

Use a simple local abstraction.

Interface approximately:

```python
class IncidentQueue:
    def add(self, incident): ...
    def next(self): ...
    def complete(self, incident_id): ...
    def fail(self, incident_id): ...
```

For now implementation may use:

- SQLite
- Python PriorityQueue
- simple local DB/storage

Do NOT depend on GCP Pub/Sub / Cloud Tasks yet unless explicitly needed.

The rest of the system should not care which queue implementation is used.

---

# 4. Investigation Orchestrator

This is the main component.

For each selected incident, create an `InvestigationContext`.

Example:

```python
InvestigationContext:
    incident

    classification
    severity

    evidence:
        logs
        machine_state
        source_code
        commits
        deployment_info
        similar_incidents
        other

    analysis:
        observations
        hypotheses
        likely_root_cause
        confidence

    proposed_fix:
        explanation
        relevant_components
        affected_files
        suggested_changes
        validation_plan
```

The context should accumulate information throughout the investigation.

---

# 5. Initial Deterministic Evidence Gathering

Some information should be gathered using rules rather than an LLM.

Examples:

If:

```text
error_timestamp = 14:32:17
```

automatically request:

```text
logs from 14:31:17 → 14:33:17
```

If:

```text
service = video-indexer
```

use configuration/service mapping to determine:

```text
repo = lumana/video-indexer
```

If deployment information is available:

```text
previous deployment
current deployment
```

fetch relevant commits/diffs automatically.

General principle:

> Use deterministic logic where the required action is obvious.  
> Use Claude when reasoning or prioritization is needed.

---

# 6. Tool / MCP Interfaces

Implement narrow interfaces even if they are initially backed by mocks.

## Logs Tool

Example functions:

```python
get_logs(
    machine_id,
    start_time,
    end_time,
    service=None
)

search_logs(
    query,
    start_time,
    end_time
)
```

Potential future backend:
- GCP Logging

For now:
- JSON fixtures are acceptable.

---

## Git Tool

Possible functions:

```python
get_commits(repo, from_time, to_time)
get_commit(commit_hash)
get_commit_diff(commit_hash)
search_code(repo, query)
get_file(repo, path, revision=None)
git_blame(repo, path, line=None)
get_recent_changes(repo, component=None)
```

Initial implementation may:
- use local git repositories
- use GitHub API
- or be stubbed

Keep the interface separate from the implementation.

---

## Machine / Telemetry Tool

Possible functions:

```python
get_machine_state(machine_id, timestamp)
get_machine_version(machine_id)
get_resource_metrics(machine_id, start_time, end_time)
```

Possible information:

```text
CPU
memory
disk
GPU
software version
architecture
restart/crash information
```

May initially return fixtures.

---

## Issue Tracker Tool

Initially output can simply be Markdown.

Later interface may support:

```python
create_ticket(report)
update_ticket(...)
```

Possible future backend:
- Jira

---

# 7. Claude Usage

Claude should NOT be used for everything.

Use it primarily for reasoning.

Suggested roles:

## A. Classification

Input:
- error
- stack trace
- metadata

Output MUST be structured.

Example:

```json
{
  "category": "application_bug",
  "severity": "high",
  "suspected_component": "stream_manager",
  "reasoning_summary": "..."
}
```

Prefer schema-validated structured output.

---

## B. Investigation Reasoning

Claude sees the current `InvestigationContext`.

It may decide it needs more information.

Example:

```text
"I suspect this started after a recent deployment.
Fetch commits deployed between T1 and T2."
```

The orchestrator then calls the Git tool.

Result is appended to `InvestigationContext`.

Claude is called again.

Conceptually:

```text
evidence
↓
Claude reasons
↓
Claude requests tool
↓
orchestrator executes tool
↓
tool result
↓
context updated
↓
Claude reasons again
```

This is the main agentic loop.

---

# 8. Investigation Loop

Possible pseudo-flow:

```python
context = build_initial_context(incident)

context += gather_rule_based_evidence(context)

while not investigation_complete(context):

    decision = claude.analyze(context)

    if decision.requests_tool:
        result = tools.execute(decision.tool_call)
        context.add(result)

    elif decision.has_sufficient_evidence:
        break

    elif max_iterations_reached:
        break
```

Need safeguards such as:

```text
max investigation iterations
max token/cost budget
tool timeout
failure handling
```

Keep these simple initially.

---

# 9. Root Cause / Proposed Fix

Do NOT jump directly from error → generated code.

Preferred output sequence:

```text
Evidence
→ observations
→ hypothesis
→ root cause
→ confidence
→ proposed fix
→ validation plan
```

Example:

```text
Root cause:
The reconnect callback may execute after StreamContext
has already been destroyed.

Evidence:
1. Stack trace terminates in reconnect().
2. All samples occur after RTSP reconnect.
3. Commit abc123 modified StreamContext ownership.
4. Failures began after deployment containing abc123.

Confidence:
0.82

Suggested fix:
Change callback lifetime management ...

Suggested validation:
1. Add reconnect regression test.
2. Reproduce failure before change.
3. Verify test passes after change.
4. Run stream integration suite.
```

For this prototype, it is NOT necessary to actually modify the repository.

The main output is investigation + proposed fix.

---

# 10. Final Report

Generate a structured report.

Initial output:
- Markdown file

Future:
- Jira ticket

Example structure:

```md
# Incident INC-123

## Severity
High

## Summary
Stream manager crashes after RTSP reconnect.

## Occurrences
17 occurrences across 3 machines.

## Original Error
...

## Relevant Logs
...

## Machine State
...

## Relevant Code
...

## Recent Commits
...

## Investigation

### Observations
...

### Root Cause Hypothesis
...

### Confidence
High / Medium / Low

## Proposed Fix
...

## Suggested Validation
...

## Relevant Links
...
```

---

# Suggested High-Level Architecture

```text
                  Incoming Incident
                         |
                         v
                +------------------+
                | Incident Manager |
                |------------------|
                | normalize        |
                | classify         |
                | deduplicate      |
                | severity         |
                +--------+---------+
                         |
                         v
                +------------------+
                | Priority Queue   |
                +--------+---------+
                         |
                         v
               +--------------------+
               | Investigation      |
               | Orchestrator       |
               |--------------------|
               | context/state      |
               | Claude loop        |
               | tool dispatch      |
               +---------+----------+
                         |
            +------------+------------+
            |            |            |
            v            v            v
       +---------+   +---------+   +----------+
       | Logs    |   | Git     |   | Machine  |
       | MCP     |   | MCP     |   | MCP      |
       +---------+   +---------+   +----------+
            |            |            |
            v            v            v
           GCP         GitHub       Telemetry
        or fixture    or local      or fixture

                         |
                         v
                    Claude API
                         |
                         v
                Investigation Report
                         |
                         v
                Markdown / Jira later
```

---

# Local Development Strategy

Prefer:

```text
Orchestrator       → local
Queue              → local
State              → SQLite/local
Claude             → real Claude API
Logs               → fixture initially, real GCP later
Git                → local repo or real read-only GitHub
Machine telemetry  → fixture initially
Output             → Markdown
```

Important open question for the team:

Does "run locally" mean:

1. everything is mocked locally

OR

2. orchestration runs locally but talks to real GCP/GitHub services?

Architect the system so both are possible.

---

# Non-Goals

DO NOT implement yet:

- Kubernetes
- distributed workers
- multiple simultaneous incidents
- autoscaling
- load balancing
- automatic deployment
- automatic merge
- unrestricted production access
- sophisticated multi-agent architecture
- complex UI
- generic enterprise agent platform
- vector DB unless clearly needed
- elaborate RAG system unless clearly needed

Keep the prototype intentionally small.

---

# Recommended Implementation Philosophy

Use this rule:

> Fake infrastructure if necessary, but keep architectural boundaries real.

Acceptable prototype shortcuts:

```text
Queue          = Python PriorityQueue
Logs           = JSON files
Machine state  = mocked JSON
Git            = local repo
Output         = Markdown
```

But keep these properly designed:

```text
IncidentInput
Incident model
IncidentQueue interface
Tool/MCP interfaces
InvestigationContext
Claude structured outputs
Agent/tool-calling loop
Orchestrator state
Report schema
```

The goal is that mocks can later be replaced by real GCP/GitHub/Jira implementations without changing investigation logic.

---

# First Suggested Milestone

Build one complete dummy scenario end-to-end.

Example:

```text
sample incident
↓
classify
↓
assign severity
↓
deduplicate
↓
enqueue
↓
dequeue
↓
fetch fake surrounding logs
↓
fetch fake machine state
↓
inspect local git history
↓
Claude investigates
↓
Claude requests another tool call
↓
tool result returned
↓
Claude forms diagnosis
↓
proposed fix generated
↓
Markdown incident report written
```

Use one deliberately-designed bug where the correct answer is known.

Do NOT start by integrating every real external system.

First prove that the orchestration architecture works.
