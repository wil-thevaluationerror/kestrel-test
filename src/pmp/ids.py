"""Exception identifiers.

IDs are derived from (period, entity, rule, subject) rather than from a counter, so the same
problem gets the same ID on every run. That is what lets a reviewer write a resolution for
an exception and have the next run recognise it.
"""

from __future__ import annotations


def slugify_subject(subject: str) -> str:
    cleaned = "".join(c.upper() if c.isalnum() else "-" for c in subject)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-")


def exception_id(period_label: str, entity_id: str, rule_id: str, subject: str = "") -> str:
    parts = ["EX", period_label, entity_id, rule_id]
    if subject:
        parts.append(slugify_subject(subject))
    return "-".join(parts)
