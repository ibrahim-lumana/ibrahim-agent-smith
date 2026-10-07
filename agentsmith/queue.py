import json
import sqlite3
from pathlib import Path
from uuid import uuid4

from agentsmith.models import Incident, IncidentInput, IncidentStatus

_SAMPLE_LIMIT = 10

_SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    incident_id TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    status TEXT NOT NULL,
    occurrence_count INTEGER NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    severity TEXT NOT NULL,
    category TEXT NOT NULL,
    suspected_component TEXT NOT NULL DEFAULT '',
    reasoning_summary TEXT NOT NULL DEFAULT '',
    classified INTEGER NOT NULL DEFAULT 0,
    investigated INTEGER NOT NULL DEFAULT 0,
    root_cause TEXT NOT NULL DEFAULT '',
    proposed_fix TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0,
    observations TEXT NOT NULL DEFAULT '[]',
    validation_plan TEXT NOT NULL DEFAULT '[]',
    verdict TEXT NOT NULL DEFAULT '',
    verdict_explanation TEXT NOT NULL DEFAULT '',
    fix_summary TEXT NOT NULL DEFAULT '',
    fix_diff TEXT NOT NULL DEFAULT '',
    pr_number INTEGER,
    pr_url TEXT NOT NULL DEFAULT '',
    latest_input TEXT NOT NULL,
    samples TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_open_fingerprint
ON incidents(fingerprint) WHERE status = 'open';
"""

_NEXT_SQL = """
SELECT * FROM incidents
WHERE status = 'open'
ORDER BY CASE severity
    WHEN 'critical' THEN 0
    WHEN 'high' THEN 1
    WHEN 'medium' THEN 2
    WHEN 'low' THEN 3
    ELSE 4
END, first_seen ASC
LIMIT 1
"""

_NEXT_UNINVESTIGATED_SQL = """
SELECT * FROM incidents
WHERE status = 'open' AND investigated = 0
ORDER BY CASE severity
    WHEN 'critical' THEN 0
    WHEN 'high' THEN 1
    WHEN 'medium' THEN 2
    WHEN 'low' THEN 3
    ELSE 4
END, first_seen ASC
LIMIT 1
"""


class IncidentQueue:
    """Local SQLite queue. next_uninvestigated is the incident the pipeline processes."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            _ensure_classification_columns(conn)
            _ensure_investigation_columns(conn)
            _ensure_verdict_columns(conn)
            _ensure_fix_columns(conn)
            _ensure_pr_columns(conn)

    def add(self, incident: Incident) -> Incident:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO incidents (
                    incident_id, fingerprint, status, occurrence_count,
                    first_seen, last_seen, severity, category,
                    suspected_component, reasoning_summary, classified,
                    investigated, root_cause, proposed_fix, confidence,
                    observations, validation_plan, verdict, verdict_explanation,
                    fix_summary, fix_diff, pr_number, pr_url, latest_input, samples
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _row_values(incident),
            )
        return incident

    def find_open_by_fingerprint(self, fingerprint: str) -> Incident | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM incidents WHERE fingerprint = ? AND status = 'open'",
                (fingerprint,),
            ).fetchone()
        if row is None:
            return None
        return _incident_from_row(row)

    def increment(self, incident_id: str, sample: IncidentInput) -> Incident:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM incidents WHERE incident_id = ?",
                (incident_id,),
            ).fetchone()
            if row is None:
                raise KeyError(incident_id)
            incident = _incident_from_row(row)
            samples = (incident.samples + [sample])[-_SAMPLE_LIMIT:]
            updated = incident.model_copy(
                update={
                    "occurrence_count": incident.occurrence_count + 1,
                    "last_seen": sample.timestamp,
                    "latest_input": sample,
                    "samples": samples,
                }
            )
            conn.execute(
                """
                UPDATE incidents
                SET occurrence_count = ?, last_seen = ?, latest_input = ?, samples = ?
                WHERE incident_id = ?
                """,
                (
                    updated.occurrence_count,
                    updated.last_seen.isoformat(),
                    updated.latest_input.model_dump_json(),
                    _dump_samples(updated.samples),
                    incident_id,
                ),
            )
        return updated

    def save_classification(self, incident: Incident) -> Incident:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE incidents
                SET category = ?, severity = ?, suspected_component = ?,
                    reasoning_summary = ?, classified = ?
                WHERE incident_id = ?
                """,
                (
                    incident.category,
                    incident.severity,
                    incident.suspected_component,
                    incident.reasoning_summary,
                    int(incident.classified),
                    incident.incident_id,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(incident.incident_id)
        return incident

    def save_investigation(self, incident: Incident) -> Incident:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE incidents
                SET investigated = ?, root_cause = ?, proposed_fix = ?, confidence = ?,
                    observations = ?, validation_plan = ?, verdict = ?, verdict_explanation = ?,
                    fix_summary = ?, fix_diff = ?, pr_number = ?, pr_url = ?
                WHERE incident_id = ?
                """,
                (
                    int(incident.investigated),
                    incident.root_cause,
                    incident.proposed_fix,
                    incident.confidence,
                    json.dumps(incident.observations),
                    json.dumps(incident.validation_plan),
                    incident.verdict,
                    incident.verdict_explanation,
                    incident.fix_summary,
                    incident.fix_diff,
                    incident.pr_number,
                    incident.pr_url,
                    incident.incident_id,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(incident.incident_id)
        return incident

    def next(self) -> Incident | None:
        with self._connect() as conn:
            row = conn.execute(_NEXT_SQL).fetchone()
        if row is None:
            return None
        return _incident_from_row(row)

    def next_uninvestigated(self) -> Incident | None:
        """Highest severity open incident that does not yet have a conclusion."""
        with self._connect() as conn:
            row = conn.execute(_NEXT_UNINVESTIGATED_SQL).fetchone()
        if row is None:
            return None
        return _incident_from_row(row)

    def complete(self, incident_id: str) -> Incident:
        return self._set_status(incident_id, "completed")

    def fail(self, incident_id: str) -> Incident:
        return self._set_status(incident_id, "failed")

    def next_incident_id(self) -> str:
        return f"INC-{uuid4().hex[:8]}"

    def _set_status(self, incident_id: str, status: IncidentStatus) -> Incident:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE incidents SET status = ? WHERE incident_id = ?",
                (status, incident_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(incident_id)
            row = conn.execute(
                "SELECT * FROM incidents WHERE incident_id = ?",
                (incident_id,),
            ).fetchone()
        return _incident_from_row(row)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection


def _row_values(incident: Incident) -> tuple:
    return (
        incident.incident_id,
        incident.fingerprint,
        incident.status,
        incident.occurrence_count,
        incident.first_seen.isoformat(),
        incident.last_seen.isoformat(),
        incident.severity,
        incident.category,
        incident.suspected_component,
        incident.reasoning_summary,
        int(incident.classified),
        int(incident.investigated),
        incident.root_cause,
        incident.proposed_fix,
        incident.confidence,
        json.dumps(incident.observations),
        json.dumps(incident.validation_plan),
        incident.verdict,
        incident.verdict_explanation,
        incident.fix_summary,
        incident.fix_diff,
        incident.pr_number,
        incident.pr_url,
        incident.latest_input.model_dump_json(),
        _dump_samples(incident.samples),
    )


def _ensure_classification_columns(connection: sqlite3.Connection) -> None:
    existing = {row["name"] for row in connection.execute("PRAGMA table_info(incidents)")}
    additions = {
        "suspected_component": "TEXT NOT NULL DEFAULT ''",
        "reasoning_summary": "TEXT NOT NULL DEFAULT ''",
        "classified": "INTEGER NOT NULL DEFAULT 0",
    }
    for name, column_type in additions.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE incidents ADD COLUMN {name} {column_type}")


def _ensure_investigation_columns(connection: sqlite3.Connection) -> None:
    existing = {row["name"] for row in connection.execute("PRAGMA table_info(incidents)")}
    additions = {
        "investigated": "INTEGER NOT NULL DEFAULT 0",
        "root_cause": "TEXT NOT NULL DEFAULT ''",
        "proposed_fix": "TEXT NOT NULL DEFAULT ''",
        "confidence": "REAL NOT NULL DEFAULT 0",
        "observations": "TEXT NOT NULL DEFAULT '[]'",
        "validation_plan": "TEXT NOT NULL DEFAULT '[]'",
    }
    for name, column_type in additions.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE incidents ADD COLUMN {name} {column_type}")


def _ensure_verdict_columns(connection: sqlite3.Connection) -> None:
    existing = {row["name"] for row in connection.execute("PRAGMA table_info(incidents)")}
    additions = {
        "verdict": "TEXT NOT NULL DEFAULT ''",
        "verdict_explanation": "TEXT NOT NULL DEFAULT ''",
    }
    for name, column_type in additions.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE incidents ADD COLUMN {name} {column_type}")


def _ensure_fix_columns(connection: sqlite3.Connection) -> None:
    existing = {row["name"] for row in connection.execute("PRAGMA table_info(incidents)")}
    additions = {
        "fix_summary": "TEXT NOT NULL DEFAULT ''",
        "fix_diff": "TEXT NOT NULL DEFAULT ''",
    }
    for name, column_type in additions.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE incidents ADD COLUMN {name} {column_type}")


def _ensure_pr_columns(connection: sqlite3.Connection) -> None:
    existing = {row["name"] for row in connection.execute("PRAGMA table_info(incidents)")}
    additions = {
        "pr_number": "INTEGER",
        "pr_url": "TEXT NOT NULL DEFAULT ''",
    }
    for name, column_type in additions.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE incidents ADD COLUMN {name} {column_type}")


def _dump_samples(samples: list[IncidentInput]) -> str:
    return json.dumps([sample.model_dump(mode="json") for sample in samples])


def _incident_from_row(row: sqlite3.Row) -> Incident:
    return Incident(
        incident_id=row["incident_id"],
        fingerprint=row["fingerprint"],
        status=row["status"],
        occurrence_count=row["occurrence_count"],
        first_seen=row["first_seen"],
        last_seen=row["last_seen"],
        severity=row["severity"],
        category=row["category"],
        suspected_component=row["suspected_component"] or "",
        reasoning_summary=row["reasoning_summary"] or "",
        classified=bool(row["classified"]),
        investigated=bool(row["investigated"]),
        root_cause=row["root_cause"] or "",
        proposed_fix=row["proposed_fix"] or "",
        confidence=float(row["confidence"] or 0),
        observations=json.loads(row["observations"] or "[]"),
        validation_plan=json.loads(row["validation_plan"] or "[]"),
        verdict=row["verdict"] or "",
        verdict_explanation=row["verdict_explanation"] or "",
        fix_summary=row["fix_summary"] or "",
        fix_diff=row["fix_diff"] or "",
        pr_number=row["pr_number"],
        pr_url=row["pr_url"] or "",
        latest_input=IncidentInput.model_validate_json(row["latest_input"]),
        samples=[
            IncidentInput.model_validate(sample) for sample in json.loads(row["samples"])
        ],
    )
