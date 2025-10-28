from __future__ import annotations

import copy
import csv
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Dict, Iterable, Optional


class PlanCache:
    """Manage cached representations of production plan datasets."""

    def __init__(self, base_dir: Path, datasets: Dict[str, Dict[str, object]]) -> None:
        self._base_dir = base_dir
        self._datasets = datasets
        self._cache: Dict[str, dict] = {}
        self._mtimes: Dict[str, Optional[float]] = {}
        self._lock = Lock()
        self._loaded_at: Optional[datetime] = None

    def refresh(self, keys: Optional[Iterable[str]] = None) -> Dict[str, dict]:
        """Force refresh for the provided dataset keys (or all)."""
        summary: Dict[str, dict] = {}
        target_keys = list(keys) if keys is not None else list(self._datasets.keys())
        with self._lock:
            for key in target_keys:
                dataset = self._load_dataset_locked(key, force=True)
                summary[key] = {
                    "entries": len(dataset.get("entries", [])),
                    "error": dataset.get("error"),
                    "updated_at": dataset.get("updated_at"),
                }
            self._loaded_at = datetime.now(timezone.utc)
        return summary

    def get_dataset(self, key: str) -> dict:
        """Return a cached dataset, auto-refreshing if the source changed."""
        with self._lock:
            dataset = self._load_dataset_locked(key, force=False)
        return dataset

    def loaded_at_iso(self) -> Optional[str]:
        if self._loaded_at is None:
            return None
        return self._loaded_at.isoformat().replace("+00:00", "Z")

    def _load_dataset_locked(self, key: str, *, force: bool) -> dict:
        if key not in self._datasets:
            raise KeyError(f"unknown dataset: {key}")

        cfg = self._datasets[key]
        filename = cfg["filename"]  # type: ignore[index]
        columns = cfg["columns"]  # type: ignore[index]
        label = cfg["label"]  # type: ignore[index]

        path = self._base_dir / filename
        result = {
            "label": label,
            "entries": [],
            "updated_at": None,
            "error": None,
        }

        if not path.exists():
            result["error"] = f"{label} not found"
            self._cache[key] = result
            self._mtimes[key] = None
            return copy.deepcopy(result)

        mtime = path.stat().st_mtime
        if not force and key in self._cache and self._mtimes.get(key) == mtime:
            return copy.deepcopy(self._cache[key])

        try:
            with path.open("r", encoding="utf-8-sig", newline="") as fh:
                reader = csv.DictReader(fh)
                headers = reader.fieldnames or []
                if headers != columns:
                    result["error"] = f"unexpected columns: {headers}"
                else:
                    entries = []
                    for row in reader:
                        entries.append({column: row.get(column, "") for column in columns})
                    result["entries"] = entries
                    result["updated_at"] = (
                        datetime.fromtimestamp(mtime, tz=timezone.utc)
                        .isoformat()
                        .replace("+00:00", "Z")
                    )
        except Exception as exc:  # pragma: no cover - logged via API response
            result["error"] = f"failed to load dataset: {exc}"

        self._cache[key] = result
        self._mtimes[key] = mtime
        return copy.deepcopy(result)


__all__ = ["PlanCache"]
