"""Gmail OAuth: one-time browser consent, then a cached, encrypted-at-rest refresh token.

Read-only scope only (gmail.readonly). Sending mail is a later, separate, CONFIRM-gated phase.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class GmailAuthError(RuntimeError):
    pass


def get_credentials(client_id: str, client_secret: str, token_path: Path) -> Credentials:
    """Return valid Credentials, refreshing or running the one-time browser flow as needed."""
    creds: Credentials | None = None
    if token_path.is_file():
        creds = Credentials.from_authorized_user_info(json.loads(token_path.read_text()), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save(creds, token_path)
            return creds
        except Exception:
            pass  # refresh token revoked/expired: fall through to a fresh consent flow

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    print("\nOpening your browser to sign in to Google and approve read-only Gmail access...")
    creds = flow.run_local_server(port=0, prompt="consent")
    _save(creds, token_path)
    return creds


def _save(creds: Credentials, token_path: Path) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())
    try:
        os.chmod(token_path, 0o600)
    except OSError:
        pass
