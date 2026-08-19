import json

import pytest

from api.storage.base import InvalidData, NotFound, Unavailable
from api.storage.local import LocalStorage


def test_profile_found(tmp_path):
    storage = LocalStorage(tmp_path); path = tmp_path / "user_profiles" / "u1.json"
    path.parent.mkdir(); path.write_text('{"user_id":"u1"}', encoding="utf-8")
    assert storage.load_profile("u1") == {"user_id": "u1"}


def test_profile_not_found(tmp_path):
    with pytest.raises(NotFound): LocalStorage(tmp_path).load_profile("missing")


def test_profile_invalid_data(tmp_path):
    path = tmp_path / "user_profiles" / "u1.json"; path.parent.mkdir(); path.write_text("bad", encoding="utf-8")
    with pytest.raises(InvalidData): LocalStorage(tmp_path).load_profile("u1")


def test_profile_save_success(tmp_path):
    LocalStorage(tmp_path).save_profile("u1", {"user_id": "u1", "value": 1})
    assert json.loads((tmp_path / "user_profiles" / "u1.json").read_text(encoding="utf-8"))["value"] == 1


def test_profile_save_failure(tmp_path):
    root = tmp_path / "blocked"; root.write_text("file", encoding="utf-8")
    with pytest.raises(Unavailable): LocalStorage(root).save_profile("u1", {"user_id": "u1"})


def test_migration_backup(tmp_path):
    storage = LocalStorage(tmp_path); storage.save_profile("u1", {"user_id": "u1"})
    storage.backup_profile_before_migration("u1")
    assert len(list((tmp_path / "user_profiles").glob("u1.*.pre_migration.bak"))) == 1


def test_profile_history(tmp_path):
    LocalStorage(tmp_path).save_profile_history("u1", "session_x", {"user_id": "u1"}, "before")
    assert len(list((tmp_path / "user_profiles" / "history").glob("*_before.json"))) == 1


def test_session_create_and_update_completed(tmp_path):
    storage = LocalStorage(tmp_path)
    metadata = {"session_id": "session_x", "user_id": "u1", "started_at": "now",
                "started_at_compact": "20260819_120000", "session_status": "started"}
    storage.create_session("session_x", metadata, "started")
    assert storage.load_session("session_x").markdown == "started"
    storage.update_session("session_x", {"session_status": "completed", "ended_at": "later"}, "done")
    result = storage.load_session("session_x")
    assert result.markdown == "done"
    assert result.metadata["session_status"] == "completed"
    assert result.metadata["ended_at"] == "later"
