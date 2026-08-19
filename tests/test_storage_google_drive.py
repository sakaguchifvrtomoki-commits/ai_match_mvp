import json
import re

import pytest

from api.storage.base import Conflict, InvalidData, NotFound, Unavailable
from api.storage.google_drive import GoogleDriveStorage
from api.storage.local import LocalStorage


class Request:
    def __init__(self, fn): self.fn = fn
    def execute(self): return self.fn()


class Files:
    def __init__(self): self.items = {}; self.next_id = 1; self.fail = False
    def _id(self): value = f"id{self.next_id}"; self.next_id += 1; return value
    def list(self, q, **kwargs):
        def run():
            if self.fail: raise RuntimeError("drive down")
            parent = re.search(r"'([^']+)' in parents", q).group(1)
            props = dict(re.findall(r"key='([^']+)' and value='([^']*)'", q))
            mime = re.search(r"mimeType = '([^']+)'", q)
            found = [dict(id=i, name=v["name"], mimeType=v.get("mimeType"), appProperties=v.get("appProperties", {}), version="1")
                     for i, v in self.items.items() if parent in v.get("parents", [])
                     and (not mime or v.get("mimeType") == mime.group(1))
                     and all(v.get("appProperties", {}).get(k) == val for k, val in props.items())]
            return {"files": found}
        return Request(run)
    def create(self, body, media_body=None, **kwargs):
        def run():
            if self.fail: raise RuntimeError("drive down")
            file_id = self._id(); content = media_body._fd.getvalue() if media_body else b""
            self.items[file_id] = {**body, "content": content}; return {"id": file_id, "version": "1"}
        return Request(run)
    def update(self, fileId, body, media_body, **kwargs):
        def run():
            if self.fail: raise RuntimeError("drive down")
            self.items[fileId].update(body); self.items[fileId]["content"] = media_body._fd.getvalue()
            return {"id": fileId, "version": "2"}
        return Request(run)
    def get_media(self, fileId, **kwargs): return Request(lambda: self.items[fileId]["content"])


class Service:
    def __init__(self): self.api = Files()
    def files(self): return self.api


@pytest.fixture
def drive():
    service = Service()
    return GoogleDriveStorage(service, "root"), service


def profile(user_id="u1"): return {"user_id": user_id, "profile_version": "0.2.1"}


def test_profile_save_and_load(drive):
    storage, _ = drive; storage.save_profile("u1", profile())
    assert storage.load_profile("u1") == profile()


def test_profile_not_found(drive):
    with pytest.raises(NotFound): drive[0].load_profile("missing")


def test_drive_failure_is_unavailable_not_not_found(drive):
    drive[1].api.fail = True
    with pytest.raises(Unavailable): drive[0].load_profile("u1")


def test_invalid_profile_json(drive):
    storage, service = drive; storage.save_profile("u1", profile())
    target = next(v for v in service.api.items.values() if v.get("appProperties", {}).get("data_type") == "current_profile")
    target["content"] = b"bad"
    with pytest.raises(InvalidData): storage.load_profile("u1")


def test_save_updates_same_profile_without_touching_other_user(drive):
    storage, service = drive; storage.save_profile("u1", profile()); storage.save_profile("u2", profile("u2"))
    updated = profile(); updated["x"] = 1; storage.save_profile("u1", updated)
    assert storage.load_profile("u1")["x"] == 1
    assert storage.load_profile("u2") == profile("u2")
    assert len([v for v in service.api.items.values() if v.get("appProperties", {}).get("data_type") == "current_profile"]) == 2


def test_profile_history(drive):
    storage, service = drive; storage.save_profile_history("u1", "s1", profile(), "before")
    assert any(v.get("appProperties", {}).get("data_type") == "profile_history" for v in service.api.items.values())


def test_migration_backup_preserves_source_bytes(drive):
    storage, service = drive; storage.save_profile("u1", profile()); storage.backup_profile_before_migration("u1")
    backup = next(v for v in service.api.items.values() if v.get("appProperties", {}).get("data_type") == "migration_backup")
    assert json.loads(backup["content"])["user_id"] == "u1"


def test_session_create_load_and_update(drive):
    storage, _ = drive
    metadata = {"session_id": "session_full_id", "user_id": "u1", "started_at_compact": "x", "session_status": "started"}
    storage.create_session("session_full_id", metadata, "start")
    assert storage.load_session("session_full_id").markdown == "start"
    storage.update_session("session_full_id", {"session_status": "completed"}, "done")
    result = storage.load_session("session_full_id")
    assert result.markdown == "done" and result.metadata["session_status"] == "completed"


def test_duplicate_session_id_conflicts(drive):
    metadata = {"session_id": "s1", "started_at_compact": "x"}
    drive[0].create_session("s1", metadata, "one")
    with pytest.raises(Conflict): drive[0].create_session("s1", metadata, "two")


def test_session_uses_full_id(drive):
    storage, _ = drive
    for sid in ("session_a_same", "session_b_same"):
        storage.create_session(sid, {"session_id": sid, "started_at_compact": "x"}, sid)
    assert storage.load_session("session_a_same").markdown == "session_a_same"
    assert storage.load_session("session_b_same").markdown == "session_b_same"


def test_missing_auth_configuration_is_unavailable(monkeypatch):
    monkeypatch.delenv("GOOGLE_DRIVE_ROOT_FOLDER_ID", raising=False)
    with pytest.raises(Unavailable): GoogleDriveStorage.from_env()


def test_default_storage_remains_local():
    from api.storage import get_storage
    assert isinstance(get_storage(), LocalStorage)
