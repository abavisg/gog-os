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
_BODY_FIELDS = {"payload", "body", "data", "raw"}

# Fields that would indicate decoded body content inside a part
_BODY_PART_FIELDS = {"body", "data"}


def _default_query() -> str:
    return os.environ.get("GMAIL_DEFAULT_QUERY", "in:inbox newer_than:2d")


def _max_results() -> int:
    try:
        return int(os.environ.get("GMAIL_MAX_RESULTS", "100"))
    except ValueError:
        return 100


def _privacy_gate(record: dict) -> None:
    """Hard-assert no body/payload data in a message record. Raises on violation."""
    for field in _BODY_FIELDS:
        if field in record:
            raise RuntimeError(
                f"PRIVACY VIOLATION: message record contains forbidden field '{field}'. "
                "Refusing to write output."
            )
    # Also check inside parts if somehow present
    parts = record.get("parts", [])
    for part in (parts if isinstance(parts, list) else []):
        for field in _BODY_PART_FIELDS:
            if field in part and part[field]:
                raise RuntimeError(
                    f"PRIVACY VIOLATION: message part contains forbidden field '{field}'. "
                    "Refusing to write output."
                )


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
            messages.append(record)

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
