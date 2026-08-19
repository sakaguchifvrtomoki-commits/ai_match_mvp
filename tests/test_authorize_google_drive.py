import json

import pytest

from scripts import authorize_google_drive as authorize_script


class FakeCredentials:
    def __init__(self, scopes=None, refresh_token="new-refresh-secret"):
        self.scopes = scopes or list(authorize_script.SCOPES)
        self.refresh_token = refresh_token

    def has_scopes(self, scopes):
        return set(scopes).issubset(set(self.scopes))

    def to_json(self):
        return json.dumps(
            {
                "token": "new-access-secret",
                "refresh_token": self.refresh_token,
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": "client-id",
                "client_secret": "client-secret",
                "scopes": self.scopes,
            }
        )


class FakeFlow:
    def __init__(self, credentials=None, error=None):
        self.credentials = credentials or FakeCredentials()
        self.error = error
        self.run_kwargs = None

    def run_local_server(self, **kwargs):
        self.run_kwargs = kwargs
        if self.error:
            raise self.error
        return self.credentials


def client_file(tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text('{"installed": {}}', encoding="utf-8")
    return path


def install_flow(monkeypatch, flow, captured=None):
    captured = captured if captured is not None else {}

    def factory(path, scopes):
        captured["path"] = path
        captured["scopes"] = scopes
        return flow

    monkeypatch.setattr(
        authorize_script.InstalledAppFlow,
        "from_client_secrets_file",
        staticmethod(factory),
    )
    return captured


def test_authorization_success_saves_credentials(monkeypatch, tmp_path):
    flow = FakeFlow()
    install_flow(monkeypatch, flow)
    token_path = tmp_path / "token.json"

    backup = authorize_script.authorize(client_file(tmp_path), token_path)

    assert backup is None
    saved = json.loads(token_path.read_text(encoding="utf-8"))
    assert saved["refresh_token"] == "new-refresh-secret"


def test_missing_client_file_fails_before_oauth(tmp_path):
    with pytest.raises(authorize_script.AuthorizationError, match="not found"):
        authorize_script.authorize(
            tmp_path / "missing.json", tmp_path / "token.json"
        )


def test_oauth_failure_does_not_create_token(monkeypatch, tmp_path):
    flow = FakeFlow(error=RuntimeError("login rejected"))
    install_flow(monkeypatch, flow)
    token_path = tmp_path / "token.json"

    with pytest.raises(authorize_script.AuthorizationError, match="authorization failed"):
        authorize_script.authorize(client_file(tmp_path), token_path)
    assert not token_path.exists()


def test_existing_token_requires_force_and_is_unchanged(monkeypatch, tmp_path):
    token_path = tmp_path / "token.json"
    token_path.write_text("old-token", encoding="utf-8")

    with pytest.raises(authorize_script.AuthorizationError, match="--force"):
        authorize_script.authorize(client_file(tmp_path), token_path)
    assert token_path.read_text(encoding="utf-8") == "old-token"


def test_force_backs_up_existing_token_before_replacement(monkeypatch, tmp_path):
    flow = FakeFlow()
    install_flow(monkeypatch, flow)
    token_path = tmp_path / "token.json"
    token_path.write_text("old-token", encoding="utf-8")

    backup = authorize_script.authorize(
        client_file(tmp_path), token_path, force=True
    )

    assert backup is not None
    assert backup.read_text(encoding="utf-8") == "old-token"
    assert json.loads(token_path.read_text(encoding="utf-8"))["token"] == (
        "new-access-secret"
    )


def test_flow_uses_drive_file_scope_and_local_server(monkeypatch, tmp_path):
    flow = FakeFlow()
    captured = install_flow(monkeypatch, flow)

    authorize_script.authorize(client_file(tmp_path), tmp_path / "token.json")

    assert captured["scopes"] == ["https://www.googleapis.com/auth/drive.file"]
    assert flow.run_kwargs == {
        "port": 0,
        "access_type": "offline",
        "prompt": "consent",
    }


def test_success_output_does_not_reveal_token(monkeypatch, tmp_path, capsys):
    flow = FakeFlow()
    install_flow(monkeypatch, flow)
    client_path = client_file(tmp_path)
    token_path = tmp_path / "token.json"

    assert authorize_script.main(
        [
            "--client-file",
            str(client_path),
            "--token-file",
            str(token_path),
        ]
    ) == 0

    output = capsys.readouterr().out
    assert "OAuth authorization succeeded." in output
    assert str(token_path.resolve()) in output
    assert "new-access-secret" not in output
    assert "new-refresh-secret" not in output
