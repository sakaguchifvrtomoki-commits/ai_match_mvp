"""Interactively authorize Fairies for Google Drive during local development."""

import argparse
import datetime
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = ["https://www.googleapis.com/auth/drive.file"]


class AuthorizationError(RuntimeError):
    """The interactive OAuth authorization or token save failed."""


def authorize(client_file: Path, token_file: Path, *, force: bool = False) -> Path | None:
    client_file = Path(client_file)
    token_file = Path(token_file)
    if not client_file.is_file():
        raise AuthorizationError(f"OAuth client file was not found: {client_file}")
    if token_file.exists() and not force:
        raise AuthorizationError(
            f"Token file already exists: {token_file}. Re-run with --force to replace it."
        )

    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_file), scopes=SCOPES
        )
        credentials = flow.run_local_server(
            port=0,
            access_type="offline",
            prompt="consent",
        )
    except Exception as exc:
        raise AuthorizationError("Google OAuth authorization failed") from exc

    if not credentials.refresh_token:
        raise AuthorizationError("OAuth authorization did not return a refresh token")
    if not credentials.has_scopes(SCOPES):
        raise AuthorizationError("OAuth credentials do not include the drive.file scope")

    try:
        token_json = credentials.to_json()
        token_data = json.loads(token_json)
    except Exception as exc:
        raise AuthorizationError("OAuth credentials could not be serialized") from exc
    if not token_data.get("refresh_token"):
        raise AuthorizationError("Serialized OAuth credentials have no refresh token")
    if not set(SCOPES).issubset(set(token_data.get("scopes") or [])):
        raise AuthorizationError("Serialized OAuth credentials have an invalid scope")

    token_file.parent.mkdir(parents=True, exist_ok=True)
    backup_path = None
    if token_file.exists():
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_path = token_file.with_name(f"{token_file.name}.{stamp}.bak")
        shutil.copy2(token_file, backup_path)

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=token_file.parent,
            prefix=f".{token_file.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(token_json)
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, token_file)
    except OSError as exc:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise AuthorizationError("OAuth token could not be saved") from exc
    return backup_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Authorize Google Drive user OAuth and save token.json."
    )
    parser.add_argument(
        "--client-file",
        default=os.getenv("GOOGLE_OAUTH_CLIENT_FILE"),
        help="Desktop OAuth credentials JSON (or GOOGLE_OAUTH_CLIENT_FILE)",
    )
    parser.add_argument(
        "--token-file",
        default=os.getenv("GOOGLE_OAUTH_TOKEN_FILE"),
        help="Output token JSON (or GOOGLE_OAUTH_TOKEN_FILE)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing token after first creating a backup",
    )
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    if not args.client_file:
        raise AuthorizationError("GOOGLE_OAUTH_CLIENT_FILE is not configured")
    if not args.token_file:
        raise AuthorizationError("GOOGLE_OAUTH_TOKEN_FILE is not configured")

    backup_path = authorize(
        Path(args.client_file), Path(args.token_file), force=args.force
    )
    print("OAuth authorization succeeded.")
    print(f"Token saved to: {Path(args.token_file).resolve()}")
    if backup_path:
        print(f"Previous token backed up to: {backup_path.resolve()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AuthorizationError as exc:
        print(f"Authorization failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
