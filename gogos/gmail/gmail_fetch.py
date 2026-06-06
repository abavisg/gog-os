"""Gmail metadata fetch — read-only, privacy gate as code.

Entry point: fetch(account) or run as python -m gogos.gmail.gmail_fetch <account>.
"""
from __future__ import annotations

import json
import os
import sys

from googleapiclient.discovery import build

from gogos.auth.google_auth import get_credentials
from gogos.paths import latest_alias, storage_path

_METADATA_HEADERS = ["From", "To", "Subject", "Date"]

# Fields that must never appear in any stored record.
_FORBIDDEN_TOP_LEVEL = {"raw", "data"}

# Keys inside payload that are safe in a metadata-format response.
_SAFE_PAYLOAD_KEYS = {"mimeType", "headers", "filename", "partId"}


def _default_query() -> str:
    return os.environ.get("GMAIL_DEFAULT_QUERY", "in:inbox newer_than:2d")


def _max_results() -> int:
    try:
        return int(os.environ.get("GMAIL_MAX_RESULTS", "100"))
    except ValueError:
        return 100


def _has_body_data(body: object) -> bool:
    """Return True if a body object contains non-empty data."""
    if not isinstance(body, dict):
        return False
    return bool(body.get("data"))


def _parts_have_body_data(parts: object) -> bool:
    """Recursively check whether any part (or nested part) carries body data."""
    if not isinstance(parts, list):
        return False
    for part in parts:
        if not isinstance(part, dict):
            continue
        if _has_body_data(part.get("body")):
            return True
        if _parts_have_body_data(part.get("parts")):
            return True
    return False


def _privacy_gate(record: dict) -> None:
    """Hard-assert the record carries no decoded body content. Raises on violation.

    Accepts a metadata-format payload envelope (payload.headers only).
    Rejects any response that contains decoded body data anywhere in the tree.
    """
    # Forbidden top-level fields (raw message content / decoded data).
    for field in _FORBIDDEN_TOP_LEVEL:
        if field in record:
            raise RuntimeError(
                f"PRIVACY VIOLATION: message record contains forbidden field '{field}'. "
                "Refusing to write output."
            )

    # Top-level body field must not contain data.
    if _has_body_data(record.get("body")):
        raise RuntimeError(
            "PRIVACY VIOLATION: message record contains non-empty 'body.data'. "
            "Refusing to write output."
        )

    # Payload: allowed only as a metadata envelope (headers + mimeType).
    # Any payload key outside the safe set, or any body data inside, is a violation.
    payload = record.get("payload")
    if payload is not None:
        if not isinstance(payload, dict):
            raise RuntimeError(
                "PRIVACY VIOLATION: 'payload' is not a dict. Refusing to write output."
            )
        unsafe_keys = set(payload.keys()) - _SAFE_PAYLOAD_KEYS
        if unsafe_keys:
            raise RuntimeError(
                f"PRIVACY VIOLATION: payload contains unexpected keys {unsafe_keys}. "
                "Refusing to write output."
            )
        if _has_body_data(payload.get("body")):
            raise RuntimeError(
                "PRIVACY VIOLATION: payload.body.data is present. "
                "Refusing to write output."
            )
        if _parts_have_body_data(payload.get("parts")):
            raise RuntimeError(
                "PRIVACY VIOLATION: payload contains parts with body data. "
                "Refusing to write output."
            )


def _project_message(record: dict) -> dict:
    """Project a raw API response to only the safe fields needed downstream.

    Extracts headers from payload.headers into a top-level 'headers' key
    (the shape that gmail_normalise expects) and drops the payload envelope.
    """
    payload = record.get("payload") or {}
    headers = payload.get("headers", []) if isinstance(payload, dict) else []

    projected: dict = {
        "id": record.get("id", ""),
        "threadId": record.get("threadId", ""),
        "labelIds": list(record.get("labelIds") or []),
        "snippet": record.get("snippet", ""),
        "headers": headers,
    }
    if "internalDate" in record:
        projected["internalDate"] = record["internalDate"]
    return projected


def _build_service(account: str):
    creds = get_credentials(account)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _list_message_ids(service, query: str, max_results: int) -> tuple[list[str], bool]:
    """Return (list_of_ids, truncated). Paginates up to max_results."""
    ids: list[str] = []
    page_token = None
    truncated = False

    while True:
        remaining = max_results - len(ids)
        kwargs: dict = {
            "userId": "me",
            "q": query,
            "maxResults": min(remaining, 500),
        }
        if page_token:
            kwargs["pageToken"] = page_token

        resp = service.users().messages().list(**kwargs).execute()
        batch = resp.get("messages", [])
        ids.extend(m["id"] for m in batch)

        if len(ids) >= max_results:
            truncated = True
            ids = ids[:max_results]
            break

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return ids, truncated


def _fetch_message(service, msg_id: str) -> dict:
    return (
        service.users()
        .messages()
        .get(
            userId="me",
            id=msg_id,
            format="metadata",
            metadataHeaders=_METADATA_HEADERS,
        )
        .execute()
    )


def fetch(account: str) -> int:
    """Fetch Gmail metadata for *account*. Returns exit code (0 = success)."""
    max_results = _max_results()
    query = _default_query()

    try:
        service = _build_service(account)
        msg_ids, truncated = _list_message_ids(service, query, max_results)

        if truncated:
            print(
                f"WARNING: result set hit GMAIL_MAX_RESULTS={max_results}. "
                "Output is truncated. Increase GMAIL_MAX_RESULTS to fetch more.",
                file=sys.stderr,
            )

        messages: list[dict] = []
        for msg_id in msg_ids:
            record = _fetch_message(service, msg_id)
            _privacy_gate(record)
            messages.append(_project_message(record))

    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    output = {
        "account": account,
        "query": query,
        "messages": messages,
        "count": len(messages),
        "truncated": truncated,
    }

    dated_dir = storage_path("gmail", account, "inbox")
    dated_file = dated_dir / "raw.json"
    dated_file.write_text(json.dumps(output, indent=2))

    alias = latest_alias(dated_dir, "latest-raw.json")
    alias.write_text(json.dumps(output, indent=2))

    print(f"OK  Wrote {len(messages)} message(s) to {alias}")
    if truncated:
        print(f"OK  truncated=true (hit max_results={max_results})", file=sys.stderr)

    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m gogos.gmail.gmail_fetch <account>", file=sys.stderr)
        sys.exit(1)
    sys.exit(fetch(sys.argv[1]))
