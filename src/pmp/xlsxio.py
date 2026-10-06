"""Deterministic xlsx writing.

openpyxl stamps the current time into the workbook properties and into every zip entry,
which would make two `make data` runs produce different file hashes for identical content.
Since file hashes are the integrity control here, generation has to be byte-stable, so the
workbook is rewritten with fixed timestamps before it lands on disk.
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

FIXED_TIMESTAMP = datetime(2026, 1, 1, 0, 0, 0)
_FIXED_ZIP_DATE = (2026, 1, 1, 0, 0, 0)
_CORE_PROPS = "docProps/core.xml"
_MODIFIED_PATTERN = re.compile(rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)")
_FIXED_MODIFIED = FIXED_TIMESTAMP.strftime("%Y-%m-%dT%H:%M:%SZ").encode()


def _freeze_core_properties(payload: bytes) -> bytes:
    """openpyxl rewrites dcterms:modified to the current time inside save(), so the only
    place to pin it is the serialised package."""
    return _MODIFIED_PATTERN.sub(rb"\g<1>" + _FIXED_MODIFIED + rb"\g<2>", payload)


def save_workbook(workbook: Workbook, path: Path) -> None:
    """Write a workbook whose bytes depend only on its contents."""
    workbook.properties.created = FIXED_TIMESTAMP
    workbook.properties.modified = FIXED_TIMESTAMP
    workbook.properties.creator = "portfolio-monitoring-pipeline"
    workbook.properties.lastModifiedBy = "portfolio-monitoring-pipeline"

    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(buffer) as source, zipfile.ZipFile(
        path, "w", compression=zipfile.ZIP_DEFLATED
    ) as target:
        for item in source.infolist():
            info = zipfile.ZipInfo(item.filename, date_time=_FIXED_ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = item.external_attr
            payload = source.read(item.filename)
            if item.filename == _CORE_PROPS:
                payload = _freeze_core_properties(payload)
            target.writestr(info, payload)
