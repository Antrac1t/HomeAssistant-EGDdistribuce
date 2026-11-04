"""Helpers for choosing a schedule (relay) from the EG.D HDO data."""
from __future__ import annotations

import re
from typing import Any, Iterable

# Regions that contain smart meter codes
SMART_REGIONS = ("SM", "TOU")

_RELAY_RE = re.compile(r"rel.(\d)")


def smart_codes(hdo_data: Iterable[dict[str, Any]]) -> list[str]:
    """Return all smart meter codes sorted for display."""
    codes = {
        record["kodHdo_A"]
        for record in hdo_data
        if record.get("region") in SMART_REGIONS and record.get("kodHdo_A")
    }
    return sorted(codes, key=lambda code: (code.casefold(), code))


def match_code(codes: list[str], text: str) -> str | None:
    """Return the code that matches the typed text: exact first, then a unique case-insensitive match."""
    text = text.strip()
    if text in codes:
        return text
    matches = [code for code in codes if code.casefold() == text.casefold()]
    return matches[0] if len(matches) == 1 else None


def _relay_number(label: str) -> int:
    match = _RELAY_RE.search(label)
    return int(match.group(1)) if match else 99


def _purposes(label: str) -> list[str]:
    """Purpose tokens of a label, e.g. 'D57d-relé1-PVTC,PV' -> ['PVTC', 'PV']."""
    return label.rsplit("-", 1)[-1].split(",")


def schedule_labels(records: Iterable[dict[str, Any]]) -> list[str]:
    """Return the distinct schedule labels of the records, ordered by relay number."""
    labels = {
        tariff["sazba"]
        for record in records
        for tariff in record.get("sazby", [])
        if tariff.get("sazba")
    }
    return sorted(labels, key=lambda label: (_relay_number(label), label))


def default_schedule(labels: list[str]) -> str | None:
    """Pick a schedule when the user made no choice: the one for PV, otherwise the first relay."""
    for label in labels:
        if "PV" in _purposes(label):
            return label
    return labels[0] if labels else None


def select_schedule(records: list[dict[str, Any]], label: str | None) -> list[dict[str, Any]]:
    """Return copies of the records that contain only the tariffs with the given label."""
    selected = []
    for record in records:
        tariffs = [t for t in record.get("sazby", []) if t.get("sazba") == label]
        if tariffs:
            selected.append({**record, "sazby": tariffs})
    return selected
