"""
v0.2.1 緊急アップデート: 実データ2件の復旧（仕様書5章）。

対象:
  - origin_260627_224857_4dd0c0       (旧: update_count 9  -> 復旧後: 10)
  - origin_260627_224857_4dd0c0_copy  (旧: update_count 10 -> 復旧後: 11)

v0.2.0のバグにより、旧プロフィール(.bak)を継承せず新規プロフィール(.json)が
上書き生成されてしまったケースを、旧プロフィールをマイグレーションした上で
このセッションの新規情報だけをマージして復旧する。

実行前に現状の .json を .pre_recovery_backup.json としてコピーしてから復旧する。
"""
import importlib.util
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("app", ROOT / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

TARGETS = [
    ("origin_260627_224857_4dd0c0", "origin_260627_224857_4dd0c0.20260726_234651.bak"),
    ("origin_260627_224857_4dd0c0_copy", "origin_260627_224857_4dd0c0_copy.20260726_231610.bak"),
]


def recover(user_id: str, bak_filename: str) -> None:
    profiles_dir = ROOT / "user_profiles"
    bak_path = profiles_dir / bak_filename
    current_path = profiles_dir / f"{user_id}.json"

    old_raw = json.loads(bak_path.read_text(encoding="utf-8"))
    reset_raw = json.loads(current_path.read_text(encoding="utf-8"))

    old = app.migrate_profile(old_raw)
    old["summary"] = app.normalize_summary(old.get("summary", ""))
    old["matching_hypothesis"] = app.normalize_matching_hypothesis(old.get("matching_hypothesis", {}))
    app.validate_profile(old)

    old_evidence = set(old.get("evidence", []))
    new_sessions = [e for e in reset_raw.get("evidence", []) if e not in old_evidence]
    if len(new_sessions) != 1:
        raise RuntimeError(
            f"{user_id}: このセッション以外の未知の差分を検出しました（new_sessions={new_sessions}）。"
            " 復旧を中止します。手動で確認してください。"
        )
    session_id = new_sessions[0]

    recovered = app.recover_reset_profile(old, reset_raw, session_id)
    app.validate_profile(recovered)

    backup_of_current = profiles_dir / f"{user_id}.pre_recovery_backup.json"
    shutil.copy2(current_path, backup_of_current)

    app.atomic_save_profile(current_path, recovered)

    print(
        f"{user_id}: recovered. "
        f"profile_update_count {old.get('profile_update_count')} -> {recovered['profile_update_count']}, "
        f"evidence={len(recovered['evidence'])}, "
        f"first_created_at={recovered['first_created_at']}, "
        f"backup_of_pre_recovery_json={backup_of_current.name}"
    )


def main() -> int:
    had_error = False
    for user_id, bak_filename in TARGETS:
        try:
            recover(user_id, bak_filename)
        except Exception as e:
            had_error = True
            print(f"{user_id}: FAILED - {type(e).__name__}: {e}", file=sys.stderr)
    return 1 if had_error else 0


if __name__ == "__main__":
    sys.exit(main())
