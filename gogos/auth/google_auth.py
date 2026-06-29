from __future__ import annotations

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES: list[str] = [
    # gmail.modify allows reading, applying/removing labels, and archiving
    # (removing INBOX). It does NOT permit permanent deletion — that requires
    # gmail.modify's delete endpoint which GogOS never calls. See gmail_apply.
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar.readonly",
]

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_TOKEN_RELATIVE = ".core/storage/auth/{account}/google_token.json"


def _token_path(account: str) -> Path:
    return _REPO_ROOT / _TOKEN_RELATIVE.format(account=account)


def _credentials_path() -> Path:
    raw = os.environ.get("GOOGLE_CREDENTIALS_PATH", "")
    if not raw:
        raise RuntimeError(
            "GOOGLE_CREDENTIALS_PATH is not set. "
            "Copy .env.example to .env and set the variable."
        )
    p = Path(raw)
    if not p.is_absolute():
        p = _REPO_ROOT / p
    if not p.exists():
        raise FileNotFoundError(
            f"Google credentials file not found at {p}. "
            "Check GOOGLE_CREDENTIALS_PATH in your .env."
        )
    return p


def _write_token(token_path: Path, creds: Credentials) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())
    token_path.chmod(0o600)


def _scopes_match(creds: Credentials) -> bool:
    stored = set(creds.scopes or [])
    wanted = set(SCOPES)
    return stored == wanted or stored.issuperset(wanted)


def get_credentials(account: str) -> Credentials:
    token_path = _token_path(account)
    creds: Credentials | None = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

        if creds.scopes and not _scopes_match(creds):
            raise RuntimeError(
                f"Stored token for '{account}' has different scopes than required. "
                f"Run /logout-google {account} first, then re-authenticate."
            )

        if creds.valid:
            return creds

        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _write_token(token_path, creds)
            return creds

    creds_path = _credentials_path()
    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    new_creds: Credentials = flow.run_local_server(port=0)  # type: ignore[assignment]
    _write_token(token_path, new_creds)
    return new_creds
