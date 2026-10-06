"""File and config hashing. Hashes are the integrity control: they prove which bytes a
report was built from and let I02 recognise a resubmitted file."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_json(payload: Any) -> str:
    """Hash a structure by its canonical JSON form, so key order cannot change the hash."""
    return sha256_text(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")))


def stable_seed(*parts: Any) -> int:
    """Seed a RNG from strings without using hash(), which is salted per process and would
    break reproducibility across runs."""
    joined = ":".join(str(p) for p in parts)
    return int(hashlib.sha256(joined.encode("utf-8")).hexdigest()[:12], 16)
