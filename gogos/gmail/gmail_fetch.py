"""Gmail metadata fetch — read-only, privacy gate as code.

Entry point: fetch(account[, window]) or run as
  python -m gogos.gmail.gmail_fetch <account> [<window>]

window values:
  yesterday  (default) — inbox from yesterday 00:00 local time until now
  all                  — full inbox, capped at 200; warns if truncated
  <N>                  — top N messages sorted by date (N is a positive integer)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, time, timedelta

from googleapiclient.discovery import build

from gogos.auth.accounts import resolve_account
from gogos.auth.google_auth import get_credentials
from gogos.paths import latest_alias, storage_path

_METADATA_HEADERS = ["From", "To", "Subject", "Date"]

# Fields that must never appear in any stored record.
_FORBIDDEN_TOP_LEVEL = {"raw", "data"}

# Keys inside payload that are safe in a metadata-format response.
_SAFE_PAYLOAD_KEYS = {"mimeType", "headers", "filename", "partId"}

_ALL_CAP = 200


def _resolve_window(window: str) -> tuple[str, int]:
    """Return (gmail_query, max_results) for the given window token."""
    w = window.strip().lower()

    if w == "yesterday":
        local_now = datetime.now().astimezone()
        yesterday_midnight = datetime.combine(
            local_now.date() - timedelta(days=1),
            time.min,
            tzinfo=local_now.tzinfo,
        )
        after_epoch = int(yesterday_midnight.timestamp())
        before_epoch = int(local_now.timestamp())
        query = f"in:inbox after:{after_epoch} before:{before_epoch}"
        return query, _ALL_CAP

    if w == "all":
        return "in:inbox", _ALL_CAP

    try:
        n = int(w)
    except ValueError:
        raise ValueError(
            f"Invalid window '{window}'. Use 'yesterday', 'all', or a positive integer."
        )
    if n < 1:
        raise ValueError(f"Window count must be a positive integer, got {n}.")
    return "in:inbox", n



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


def fetch(account: str, window: str = "yesterday") -> int:
    """Fetch Gmail metadata for *account*. Returns exit code (0 = success).

    window: 'yesterday' (default), 'all', or a positive integer as a string.
    """
    try:
        account = resolve_account(account)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    try:
        query, max_results = _resolve_window(window)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    is_all = window.strip().lower() == "all"

    try:
        service = _build_service(account)
        msg_ids, truncated = _list_message_ids(service, query, max_results)

        if truncated and is_all:
            print(
                f"WARNING: 'all' returned more than {_ALL_CAP} messages. "
                f"Output is capped at {_ALL_CAP}.",
                file=sys.stderr,
            )
        elif truncated:
            print(
                f"WARNING: result set hit limit={max_results}. "
                "Output is truncated.",
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
        "window": window,
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
        print(
            "Usage: python -m gogos.gmail.gmail_fetch <account> [yesterday|all|<N>]",
            file=sys.stderr,
        )
        sys.exit(1)
    _window = sys.argv[2] if len(sys.argv) > 2 else "yesterday"
    sys.exit(fetch(sys.argv[1], _window))
