"""Append-only execution journal for HAM-on-X manual canaries."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.redaction import redact
from src.ham.ham_x.review_queue import _cap


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


class ExecutionJournal:
    def __init__(self, *, path: Path | None = None, config: HamXConfig | None = None) -> None:
        cfg = config or load_ham_x_config()
        self.path = path or cfg.execution_journal_path

    def records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
        return rows

    def has_executed(self, *, action_id: str, idempotency_key: str) -> bool:
        for row in self.records():
            if row.get("status") != "executed":
                continue
            if row.get("action_id") == action_id or row.get("idempotency_key") == idempotency_key:
                return True
        return False

    def daily_executed_count(self, *, day: str | None = None) -> int:
        target = day or _today()
        return sum(
            1
            for row in self.records()
            if row.get("status") == "executed" and str(row.get("executed_at", "")).startswith(target)
        )

    def append_executed(
        self,
        *,
        action_id: str,
        idempotency_key: str,
        action_type: str,
        provider_post_id: str | None,
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "action_id": action_id,
            "idempotency_key": idempotency_key,
            "action_type": action_type,
            "provider_post_id": provider_post_id,
            "status": "executed",
            "executed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(_cap(redact(row)), sort_keys=True, ensure_ascii=True, default=str) + "\n")
