"""Small pre-sink sanitization layer for runtime evidence.

This module is deliberately not an authenticity boundary. It protects known
credentials before evidence or convenience output is clipped, serialized, or
persisted by the runner.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA = "opencode-eval-runner/evidence-safety/v1"
REDACTED = "***REDACTED***"
OMITTED = object()
SUPPORTED_JSON_ESCAPE_LAYERS = 3
JSON_SOURCE_LIMIT = 4_000_000
MAX_DEPTH = 32
MAX_NODES = 20_000

REASONS = frozenset({
    "credential_match",
    "sensitive_key",
    "size_limit",
    "missing",
    "unsupported_representation",
    "credential_inventory_unavailable",
    "event_limit",
})


def sensitive_key(key: str) -> bool:
    key = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", key)
    key = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    normalized = "_".join(re.findall(r"[a-z0-9]+", key.lower()))
    return (
        normalized in {"key", "apikey", "api_key", "access", "refresh", "token"}
        or normalized.endswith(("_key", "_token"))
        or any(
            normalized == value or normalized.endswith("_" + value)
            for value in ("secret", "password", "credential", "authorization", "cookie")
        )
    )


class UnsafeEvidence(ValueError):
    def __init__(self, reason: str):
        if reason not in REASONS:
            reason = "unsupported_representation"
        super().__init__(reason)
        self.reason = reason


def _owned(value: Any, depth: int = 0, budget: list[int] | None = None) -> Any:
    budget = [MAX_NODES] if budget is None else budget
    budget[0] -= 1
    if depth > MAX_DEPTH or budget[0] < 0:
        raise UnsafeEvidence("unsupported_representation")
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise UnsafeEvidence("unsupported_representation")
        return value
    if type(value) is str:
        try:
            value.encode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise UnsafeEvidence("unsupported_representation") from exc
        return value
    if type(value) is list:
        return [_owned(item, depth + 1, budget) for item in value]
    if type(value) is dict:
        if not all(type(key) is str for key in value):
            raise UnsafeEvidence("unsupported_representation")
        return {key: _owned(item, depth + 1, budget) for key, item in value.items()}
    raise UnsafeEvidence("unsupported_representation")


def _encoded_size(value: Any) -> int:
    try:
        return len(
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError) as exc:
        raise UnsafeEvidence("unsupported_representation") from exc


def _collect_sensitive_values(value: Any, out: set[str], depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise UnsafeEvidence("credential_inventory_unavailable")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise UnsafeEvidence("credential_inventory_unavailable")
            if sensitive_key(key):
                _collect_scalar_credentials(item, out)
            _collect_sensitive_values(item, out, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _collect_sensitive_values(item, out, depth + 1)


def _collect_scalar_credentials(value: Any, out: set[str]) -> None:
    if isinstance(value, str):
        try:
            nested = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            if value:
                out.add(value)
            return
        if isinstance(nested, (dict, list)):
            _collect_sensitive_values(nested, out)
            return
        if value:
            out.add(value)
        return
    if type(value) in (int, float) and not isinstance(value, bool):
        if type(value) is float and not math.isfinite(value):
            return
        out.add(json.dumps(value, allow_nan=False))
    elif isinstance(value, (dict, list)):
        _collect_sensitive_values(value, out)


def _json_source_credentials(path: Path, out: set[str]) -> bool:
    if not path.is_file():
        return True
    try:
        if path.stat().st_size > JSON_SOURCE_LIMIT:
            return False
        value = json.loads(path.read_text(encoding="utf-8"))
        _collect_sensitive_values(value, out)
        return True
    except (OSError, UnicodeError, json.JSONDecodeError, UnsafeEvidence, RecursionError):
        return False


def _database_credentials(path: Path, out: set[str]) -> bool:
    if not path.is_file():
        return True
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            columns = [row[1] for row in db.execute('PRAGMA table_info("credential")')]
            if not columns:
                return True
            quoted = ", ".join('"' + col.replace('"', '""') + '"' for col in columns)
            for row in db.execute(f'SELECT {quoted} FROM "credential"'):
                for column, value in zip(columns, row):
                    if value is None or isinstance(value, bytes):
                        continue
                    if sensitive_key(column) or column.lower() in {"data", "value", "payload"}:
                        _collect_scalar_credentials(value, out)
                    elif isinstance(value, str) and value.lstrip().startswith(("{", "[")):
                        try:
                            nested = json.loads(value)
                        except json.JSONDecodeError:
                            continue
                        _collect_sensitive_values(nested, out)
        return True
    except (sqlite3.Error, OSError, UnsafeEvidence, RecursionError):
        return False


class Sanitizer:
    def __init__(self, credentials: Iterable[str] = (), *, inventory_complete: bool = True):
        values = {value for value in credentials if isinstance(value, str) and value}
        self.credentials = tuple(sorted(values, key=lambda value: (-len(value), value)))
        self.inventory_complete = inventory_complete

        variants = set(self.credentials)
        frontier = set(self.credentials)
        for _ in range(SUPPORTED_JSON_ESCAPE_LAYERS):
            generated = {
                json.dumps(value, ensure_ascii=ascii_only)[1:-1]
                for value in frontier
                for ascii_only in (False, True)
            } - variants
            variants.update(generated)
            frontier = generated

        self._matcher = (
            re.compile(
                "|".join(
                    re.escape(value)
                    for value in sorted(variants, key=lambda value: (-len(value), value))
                )
            )
            if variants
            else None
        )

    @classmethod
    def from_runtime(
        cls,
        env: Mapping[str, str],
        *,
        json_sources: Iterable[Path] = (),
        database_sources: Iterable[Path] = (),
    ) -> "Sanitizer":
        values: set[str] = set()
        for name, value in env.items():
            if isinstance(value, str) and value and sensitive_key(name):
                values.add(value)

        complete = True
        for path in json_sources:
            complete = _json_source_credentials(path, values) and complete
        for path in database_sources:
            complete = _database_credentials(path, values) and complete
        return cls(values, inventory_complete=complete)

    def matches(self, value: str) -> bool:
        return self._matcher is not None and self._matcher.search(value) is not None

    def redact_text(self, value: str) -> tuple[str, bool]:
        if not self.inventory_complete:
            return REDACTED, True
        if self._matcher is None:
            return value, False
        safe = self._matcher.sub(REDACTED, value)
        return safe, safe != value

    def evidence_value(self, value: Any) -> tuple[Any, bool]:
        if not self.inventory_complete:
            raise UnsafeEvidence("credential_inventory_unavailable")
        value = _owned(value)
        return self._evidence_value(value)

    def _evidence_value(self, value: Any) -> tuple[Any, bool]:
        if type(value) is str:
            return self.redact_text(value)
        if type(value) is list:
            safe_items = []
            changed = False
            for item in value:
                safe, item_changed = self._evidence_value(item)
                safe_items.append(safe)
                changed = changed or item_changed
            return safe_items, changed
        if type(value) is dict:
            if any(sensitive_key(key) or self.matches(key) for key in value):
                raise UnsafeEvidence("sensitive_key")
            safe: dict[str, Any] = {}
            changed = False
            for key, item in value.items():
                safe_item, item_changed = self._evidence_value(item)
                safe[key] = safe_item
                changed = changed or item_changed
            return safe, changed
        if value is None or type(value) is bool:
            return value, False

        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        if encoded in self.credentials:
            raise UnsafeEvidence("credential_match")
        return value, False

    def output_value(self, value: Any) -> Any:
        if not self.inventory_complete:
            return REDACTED
        try:
            value = _owned(value)
        except UnsafeEvidence:
            return REDACTED
        return self._output_value(value)

    def _output_value(self, value: Any) -> Any:
        if type(value) is dict:
            safe: dict[str, Any] = {}
            for child_key, item in value.items():
                if self.matches(child_key):
                    return {"__omitted__": "sensitive_key"}
                if sensitive_key(child_key):
                    safe[child_key] = REDACTED
                else:
                    safe[child_key] = self._output_value(item)
            return safe
        if type(value) is list:
            return [self._output_value(item) for item in value]
        if type(value) is str:
            return self.redact_text(value)[0]
        if value is None or type(value) is bool:
            return value

        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        return REDACTED if encoded in self.credentials else value

    def json_lines(self, text: str) -> tuple[str, bool]:
        if not text:
            return text, False

        safe_lines: list[str] = []
        changed = False
        for line in text.splitlines():
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                safe, line_changed = self.redact_text(line)
                safe_lines.append(safe)
                changed = changed or line_changed
                continue

            safe = self.output_value(parsed)
            encoded = json.dumps(
                safe,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
            safe_lines.append(encoded)
            changed = changed or encoded != line

        suffix = "\n" if text.endswith("\n") else ""
        return "\n".join(safe_lines) + suffix, changed


class Projection:
    def __init__(self, sanitizer: Sanitizer, *, stage: str = "before_sink"):
        self.sanitizer = sanitizer
        self.stage = stage
        self.fields: list[dict[str, Any]] = []
        self.losses = {reason: 0 for reason in REASONS}

    def _record(
        self,
        field: str,
        state: str,
        *,
        event: int | None,
        reason: str | None = None,
    ) -> None:
        item: dict[str, Any] = {"event": event, "field": field, "state": state}
        if reason is not None:
            item.update({"reason": reason, "stage": self.stage})
            self.losses[reason] += 1
        self.fields.append(item)

    def omit(self, field: str, reason: str, *, event: int | None = None) -> object:
        if reason not in REASONS:
            reason = "unsupported_representation"
        self._record(field, "omitted", event=event, reason=reason)
        return OMITTED

    def field(
        self,
        field: str,
        value: Any = OMITTED,
        *,
        event: int | None = None,
        limit: int = 6000,
        protocol: bool = False,
    ) -> Any:
        if value is OMITTED:
            return self.omit(field, "missing", event=event)
        try:
            if protocol:
                safe = _owned(value)
                changed = False
            else:
                safe, changed = self.sanitizer.evidence_value(value)
            if _encoded_size(safe) > limit:
                return self.omit(field, "size_limit", event=event)
        except UnsafeEvidence as exc:
            return self.omit(field, exc.reason, event=event)
        except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError):
            return self.omit(field, "unsupported_representation", event=event)

        if changed:
            self._record(field, "redacted", event=event, reason="credential_match")
        else:
            self._record(field, "exact", event=event)
        return safe

    def loss(self, reason: str, *, count: int = 1) -> None:
        if reason not in REASONS:
            reason = "unsupported_representation"
        self.losses[reason] += max(count, 0)

    def summary(self) -> dict[str, Any]:
        losses = {key: value for key, value in self.losses.items() if value}
        return {
            "schema": SCHEMA,
            "inventory_complete": self.sanitizer.inventory_complete,
            "evidence_eligible": self.sanitizer.inventory_complete and not losses,
            "fields": self.fields,
            "losses": losses,
        }
