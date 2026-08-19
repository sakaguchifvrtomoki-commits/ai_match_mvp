import datetime
import json
import shutil
from pathlib import Path

from api.storage.base import InvalidData, NotFound, SessionData, Storage, Unavailable


class LocalStorage(Storage):
    def __init__(self, root: Path):
        self.root = Path(root)

    def _profile_path(self, user_id): return self.root / "user_profiles" / f"{user_id}.json"
    def _sessions_dir(self): return self.root / "logs" / "0.2.2" / "sessions"

    def load_profile(self, user_id: str) -> dict:
        path = self._profile_path(user_id)
        if not path.exists(): raise NotFound(f"profile not found: {user_id}")
        try: data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc: raise InvalidData("profile JSON is invalid") from exc
        except OSError as exc: raise Unavailable("profile storage is unavailable") from exc
        if not isinstance(data, dict): raise InvalidData("profile must be an object")
        return data

    def save_profile(self, user_id: str, profile: dict) -> None:
        path = self._profile_path(user_id); temp = path.with_suffix(".json.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
            saved = json.loads(temp.read_text(encoding="utf-8"))
            if saved.get("user_id") != profile.get("user_id"): raise InvalidData("user_id mismatch")
            temp.replace(path)
        except InvalidData: raise
        except (OSError, TypeError, ValueError) as exc: raise Unavailable("profile could not be saved") from exc

    def save_profile_history(self, user_id, session_id, profile, stage):
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = "_before" if stage == "before" else ""
        path = self.root / "user_profiles" / "history" / f"{user_id}_{stamp}_{session_id}{suffix}.json"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
        except (OSError, TypeError, ValueError) as exc: raise Unavailable("profile history could not be saved") from exc

    def backup_profile_before_migration(self, user_id):
        source = self._profile_path(user_id)
        if not source.exists(): raise NotFound(f"profile not found: {user_id}")
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        try: shutil.copy2(source, source.with_suffix(f".{stamp}.pre_migration.bak"))
        except OSError as exc: raise Unavailable("migration backup could not be saved") from exc

    def create_session(self, session_id, metadata, markdown):
        base = self._sessions_dir(); stamp = metadata["started_at_compact"]; short = session_id.rsplit("_", 1)[-1]
        log = base / f"session_{stamp}_v0.2.2_{short}.md"; meta = log.with_suffix(".json")
        data = dict(metadata); data.pop("started_at_compact", None); data["log_path"] = str(log)
        try:
            base.mkdir(parents=True, exist_ok=True); log.write_text(markdown, encoding="utf-8")
            meta.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except (OSError, TypeError, ValueError) as exc:
            try: log.unlink(missing_ok=True)
            except OSError: pass
            raise Unavailable("session could not be created") from exc

    def load_session(self, session_id):
        base = self._sessions_dir(); suffix = session_id.rsplit("_", 1)[-1]; found = list(base.glob(f"*{suffix}.json"))
        if len(found) == 0: raise NotFound(f"session not found: {session_id}")
        if len(found) != 1: raise InvalidData("multiple session records found")
        try:
            metadata = json.loads(found[0].read_text(encoding="utf-8")); log = Path(metadata["log_path"])
            markdown = log.read_text(encoding="utf-8") if log.exists() else ""
        except (json.JSONDecodeError, KeyError, TypeError) as exc: raise InvalidData("session metadata is invalid") from exc
        except OSError as exc: raise Unavailable("session storage is unavailable") from exc
        return SessionData(metadata, markdown)

    def update_session(self, session_id, metadata, markdown):
        existing = self.load_session(session_id); data = dict(existing.metadata); data.update(metadata)
        log = Path(data["log_path"]); suffix = session_id.rsplit("_", 1)[-1]; meta = list(self._sessions_dir().glob(f"*{suffix}.json"))[0]
        try:
            log.write_text(markdown, encoding="utf-8")
            meta.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except (OSError, TypeError, ValueError) as exc: raise Unavailable("session could not be updated") from exc
