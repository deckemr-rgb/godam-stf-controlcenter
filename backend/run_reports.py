"""Read-only job reporting; a finished worker is not proof of social activity."""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORT_DIR = Path(os.getenv("COMMENT_STATE_DIR", "/data/comment-state")) / "farm-reports"
RUN_ID = re.compile(r"^[a-f0-9]{32}$")
TERMINAL = {"completed", "error", "stopped", "missing", "interrupted"}


def summarize(report: dict[str, Any]) -> dict[str, Any]:
    jobs = []
    for original in report.get("jobs", []):
        job = {key: value for key, value in original.items() if key != "token"}
        state = job.get("status", "missing")
        result = job.get("result") or {}
        if state in {"error", "missing", "interrupted"}:
            outcome = "error"
        elif state == "stopped":
            outcome = "stopped"
        elif state == "completed":
            # "Nol komentar" hanya relevan bila komentar memang diminta.
            actions = result.get("actions") or []
            if result.get("comments_posted") == 0 and (not actions or "comment" in actions):
                outcome = "no_comments_recorded"
            else:
                outcome = "unverified"
        else:
            outcome = "running"
        job["outcome"] = outcome
        job["verified"] = False  # Legacy worker has no independent success verification.
        jobs.append(job)
    counts = {name: sum(job["outcome"] == name for job in jobs)
              for name in ("running", "error", "stopped", "no_comments_recorded", "unverified")}
    if counts["running"]:
        status = "running"
    elif jobs and counts["error"] == len(jobs):
        status = "error"
    elif jobs and counts["stopped"] == len(jobs):
        status = "stopped"
    else:
        status = "needs_review"
    return {**report, "jobs": jobs, "status": status, "summary": {
        **counts, "total": len(jobs), "verified": 0,
        "completed": sum(job.get("status") == "completed" for job in jobs),
    }}


def save_report(report: dict[str, Any]) -> None:
    """Persist terminal reports only, never credentials or executable sessions."""
    if not RUN_ID.fullmatch(report["run_id"]):
        raise ValueError("Invalid run ID")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    payload = summarize(report)
    payload["saved_at"] = datetime.now(timezone.utc).isoformat()
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=REPORT_DIR,
                                     suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(payload, handle, ensure_ascii=False)
    try:
        os.replace(temporary, REPORT_DIR / f"{report['run_id']}.json")
    finally:
        temporary.unlink(missing_ok=True)


def read_report(run_id: str) -> dict[str, Any] | None:
    if not RUN_ID.fullmatch(run_id):
        return None
    try:
        report = json.loads((REPORT_DIR / f"{run_id}.json").read_text(encoding="utf-8"))
        if not isinstance(report, dict) or not isinstance(report.get("jobs"), list):
            return None
        return {**summarize(report), "archived": True}
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def list_reports() -> list[dict[str, Any]]:
    if not REPORT_DIR.is_dir():
        return []
    paths = sorted(REPORT_DIR.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    return [report for path in paths[:100] if (report := read_report(path.stem))]
