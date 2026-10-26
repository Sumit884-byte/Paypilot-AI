"""Fuzzy match a lender or app name against an RBI digital-lending-app list.

The shipped snapshot has no entries. Names are accepted only when the file records
an rbi.org.in source URL and a retrieval time, or when a live fetch is explicitly
enabled and the official HTML contains a recognizable table. A miss is a potential
warning, never a confirmed regulatory violation. Names are not invented here.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional

import httpx

SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "reference" / "rbi_dla_snapshot.json"
DEFAULT_SOURCE_URL = "https://www.rbi.org.in/Scripts/bs_viewcontent.aspx?Id=4413"
SOURCE_NAME = "Reserve Bank of India list of digital lending apps of NBFCs"
MATCH_THRESHOLD = 0.90
_MEMORY: dict[str, Any] | None = None


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _normalise(name: str) -> str:
    text = name.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\b(private|pvt|ltd|limited)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_rbi_html(html: str) -> list[dict[str, str]]:
    """Extract NBFC and app columns only from a table whose header says so.

    Anything else, including navigation links, is ignored so a failed page parse
    cannot be stored as a list of lenders.
    """
    if "digital lending" not in html.casefold() or "<table" not in html.casefold():
        return []
    rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", html, flags=re.IGNORECASE | re.DOTALL)
    header_index = None
    parsed_rows: list[list[str]] = []
    for row in rows:
        cells = [
            re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cell)).strip()
            for cell in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row, flags=re.IGNORECASE | re.DOTALL)
        ]
        cells = [cell for cell in cells if cell]
        if not cells:
            continue
        parsed_rows.append(cells)
        joined = " ".join(cells).casefold()
        if header_index is None and "app" in joined and ("nbfc" in joined or "name of the" in joined):
            header_index = len(parsed_rows) - 1
    if header_index is None:
        return []
    header = [cell.casefold() for cell in parsed_rows[header_index]]
    app_at = next((i for i, cell in enumerate(header) if "app" in cell), None)
    name_at = next((i for i, cell in enumerate(header) if "nbfc" in cell or "entity" in cell or "name" in cell), None)
    if app_at is None or name_at is None:
        return []
    entries = []
    for cells in parsed_rows[header_index + 1:]:
        if max(app_at, name_at) >= len(cells):
            continue
        nbfc_name = cells[name_at].strip()
        app_name = cells[app_at].strip()
        if not nbfc_name or not app_name or nbfc_name.casefold() == "nbfc":
            continue
        if len(nbfc_name) > 160 or len(app_name) > 160:
            continue
        entries.append({"nbfc_name": nbfc_name, "app_name": app_name})
    return entries


def _usable_snapshot(payload: Any) -> Optional[dict[str, Any]]:
    if not isinstance(payload, dict):
        return None
    url = str(payload.get("source_url") or "")
    if not (url.startswith("https://www.rbi.org.in/") or url.startswith("https://rbi.org.in/")):
        return None
    retrieved = payload.get("retrieved_at")
    entries = payload.get("entries")
    if not isinstance(retrieved, str) or not retrieved.strip() or not isinstance(entries, list):
        return None
    clean = []
    for entry in entries:
        if not isinstance(entry, dict):
            return None
        nbfc_name = entry.get("nbfc_name")
        app_name = entry.get("app_name")
        if not isinstance(nbfc_name, str) or not isinstance(app_name, str):
            return None
        if nbfc_name.strip() and app_name.strip():
            clean.append({"nbfc_name": nbfc_name.strip(), "app_name": app_name.strip()})
    if not clean:
        return None
    return {
        "source_name": payload.get("source_name") or SOURCE_NAME,
        "source_url": url,
        "retrieved_at": retrieved,
        "entries": clean,
        "load_status": "local_snapshot",
    }


def fetch_official_list(url: str = DEFAULT_SOURCE_URL, timeout: float = 8.0) -> Optional[dict[str, Any]]:
    """Retrieve and parse the official page. Returns None when the list is not usable."""
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": "PayScoreDemo/offer-guard"})
            response.raise_for_status()
            html = response.text
    except httpx.HTTPError:
        return None
    entries = parse_rbi_html(html)
    if not entries:
        return None
    return {
        "source_name": SOURCE_NAME,
        "source_url": url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "entries": entries,
        "load_status": "fetched",
    }


def load_directory(snapshot_path: Optional[Path] = None, allow_network: Optional[bool] = None) -> dict[str, Any]:
    """Return a directory payload. Network is off unless PAYSCORE_RBI_FETCH is true."""
    global _MEMORY
    path = Path(snapshot_path) if snapshot_path else SNAPSHOT_PATH
    if allow_network is None:
        allow_network = _enabled("PAYSCORE_RBI_FETCH")
    cache_key = f"{path}:{allow_network}"
    if _MEMORY and _MEMORY.get("key") == cache_key:
        return _MEMORY["value"]
    loaded = None
    if path.is_file():
        try:
            loaded = _usable_snapshot(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            loaded = None
    if loaded is None and allow_network:
        loaded = fetch_official_list()
    if loaded is None:
        loaded = {
            "source_name": SOURCE_NAME,
            "source_url": DEFAULT_SOURCE_URL,
            "retrieved_at": None,
            "entries": [],
            "load_status": "unavailable",
        }
    _MEMORY = {"key": cache_key, "value": loaded}
    return loaded


def clear_directory_cache() -> None:
    global _MEMORY
    _MEMORY = None


def match_lender(name: str, directory: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    directory = directory if directory is not None else load_directory()
    entries = directory.get("entries") or []
    base = {
        "source_name": directory.get("source_name") or SOURCE_NAME,
        "source_url": directory.get("source_url") or DEFAULT_SOURCE_URL,
        "retrieved_at": directory.get("retrieved_at"),
        "load_status": directory.get("load_status"),
        "entries_loaded": len(entries),
        "confirmed_violation": False,
        "matched_name": None,
        "matched_field": None,
        "similarity": None,
    }
    if not entries or directory.get("load_status") == "unavailable":
        return {
            **base,
            "status": "unverified",
            "rbi_directory_match": "unverified",
            "warning": (
                "The RBI digital-lending-app list could not be verified from a retrieved snapshot. "
                "This is not a regulatory finding."
            ),
        }
    query = _normalise(name or "")
    if len(query) < 4:
        return {
            **base,
            "status": "no_match",
            "rbi_directory_match": "no_match",
            "warning": "The lender name is too short to match. This is not a confirmed violation.",
        }
    best_score = 0.0
    best_name = None
    best_field = None
    for entry in entries:
        for field in ("nbfc_name", "app_name"):
            candidate = _normalise(str(entry.get(field) or ""))
            if len(candidate) < 4:
                continue
            score = 1.0 if candidate == query else SequenceMatcher(None, query, candidate).ratio()
            if score > best_score:
                best_score = score
                best_name = entry.get(field)
                best_field = field
    if best_name is not None and best_score >= MATCH_THRESHOLD:
        return {
            **base,
            "status": "possible_match",
            "rbi_directory_match": "match",
            "matched_name": best_name,
            "matched_field": best_field,
            "similarity": round(best_score, 4),
            "warning": (
                "Possible name match against the retrieved list. A name match does not confirm that "
                "this offer, or this legal entity, is authorised."
            ),
        }
    return {
        **base,
        "status": "no_match",
        "rbi_directory_match": "no_match",
        "matched_name": best_name,
        "matched_field": best_field,
        "similarity": round(best_score, 4) if best_name else None,
        "warning": (
            "No close name was found in the retrieved list. This is a potential warning, not a confirmed "
            "regulatory violation."
        ),
    }
