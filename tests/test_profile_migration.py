import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('app', Path(__file__).resolve().parents[1] / 'app.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

FIXTURES_DIR = Path(__file__).resolve().parent / 'fixtures' / 'profile_migration'
FIXTURE_012 = FIXTURES_DIR / 'profile_v012.json'
FIXTURE_013 = FIXTURES_DIR / 'profile_v013.json'


def _load_fixture(path):
    return json.loads(path.read_text(encoding='utf-8'))


def _write_profile(path, profile):
    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding='utf-8')


def _use_tmp_profiles_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, 'get_user_profiles_dir', lambda: tmp_path)


# ===========================================================================
# T001: v0.1.2 -> v0.2.1
# ===========================================================================

def test_t001_migrate_012_fixture_to_021(monkeypatch, tmp_path):
    _use_tmp_profiles_dir(monkeypatch, tmp_path)
    fixture = _load_fixture(FIXTURE_012)
    user_id = fixture['user_id']
    _write_profile(tmp_path / f'{user_id}.json', fixture)

    profile = mod.load_user_profile(user_id)

    assert profile['profile_version'] == mod.CURRENT_PROFILE_VERSION
    assert profile['profile_update_count'] == fixture['profile_update_count']
    assert profile['first_created_at'] == fixture['first_created_at']
    assert profile['values'] == fixture['values']
    assert profile['summary']['stable'] == fixture['summary']['stable']
    assert profile['summary']['tensions'] == fixture['summary']['tensions']
    assert set(fixture['evidence']).issubset(set(profile['evidence']))
    assert profile['summary']['stable_candidates'] == []
    for field in ['communication_style', 'decision_style', 'emotional_tendency']:
        stub = profile['personality_trait_candidates'][field]
        assert len(stub) == 1
        assert stub[0]['description'] == fixture['personality_traits'][field]
        assert stub[0]['canonical_key'].startswith('legacy_')
    topic_meta = profile['preferences']['conversation_topic_metadata']
    assert {m['display_name'] for m in topic_meta} == set(fixture['preferences']['conversation_topics'])
    assert profile['matching_hypothesis']['stable_candidates'] == []

    saved = json.loads((tmp_path / f'{user_id}.json').read_text(encoding='utf-8'))
    assert saved['profile_version'] == mod.CURRENT_PROFILE_VERSION
    assert saved['profile_update_count'] == fixture['profile_update_count']


# ===========================================================================
# T002: v0.1.3 -> v0.2.1
# ===========================================================================

def test_t002_migrate_013_fixture_to_021(monkeypatch, tmp_path):
    _use_tmp_profiles_dir(monkeypatch, tmp_path)
    fixture = _load_fixture(FIXTURE_013)
    user_id = fixture['user_id']
    _write_profile(tmp_path / f'{user_id}.json', fixture)

    profile = mod.load_user_profile(user_id)

    assert profile['profile_version'] == mod.CURRENT_PROFILE_VERSION
    stable_candidates = profile['summary']['stable_candidates']
    assert len(stable_candidates) == len(fixture['summary']['stable_candidates'])
    for candidate in stable_candidates:
        assert candidate['canonical_key']
        assert candidate['canonical_key'].startswith('legacy_')
    original_descriptions = {c['description'] for c in fixture['summary']['stable_candidates']}
    migrated_descriptions = {c['description'] for c in stable_candidates}
    assert original_descriptions == migrated_descriptions


# ===========================================================================
# T003: 現在バージョンの読み込み
# ===========================================================================

def test_t003_current_version_loaded_unchanged(monkeypatch, tmp_path):
    _use_tmp_profiles_dir(monkeypatch, tmp_path)
    profile = mod._empty_profile('u_current')
    profile['profile_update_count'] = 3
    profile['evidence'] = ['s1', 's2']
    path = tmp_path / 'u_current.json'
    _write_profile(path, profile)
    before_bytes = path.read_bytes()

    loaded = mod.load_user_profile('u_current')

    assert loaded['profile_update_count'] == 3
    assert loaded['evidence'] == ['s1', 's2']
    after_bytes = path.read_bytes()
    assert before_bytes == after_bytes  # no rewrite happened for an already-current profile


def test_t003_reloading_current_version_does_not_duplicate_candidates(monkeypatch, tmp_path):
    _use_tmp_profiles_dir(monkeypatch, tmp_path)
    profile = mod._empty_profile('u_current2')
    profile['summary']['stable_candidates'] = [{
        'description': 'd1', 'canonical_key': 'd1', 'status': 'candidate', 'support_count': 1,
        'first_seen_session_id': 's1', 'last_seen_session_id': 's1', 'evidence': ['s1'], 'confidence': 0.5,
    }]
    _write_profile(tmp_path / 'u_current2.json', profile)

    first = mod.load_user_profile('u_current2')
    second = mod.load_user_profile('u_current2')

    assert len(first['summary']['stable_candidates']) == 1
    assert len(second['summary']['stable_candidates']) == 1


# ===========================================================================
# T004: 複数バージョンをまたぐ移行
# ===========================================================================

def test_t004_migrates_through_every_step_from_010(monkeypatch):
    call_counts = {version: 0 for version in mod.MIGRATIONS}
    wrapped = {}
    for version, fn in mod.MIGRATIONS.items():
        def make_wrapper(v, f):
            def wrapper(profile):
                call_counts[v] += 1
                return f(profile)
            return wrapper
        wrapped[version] = make_wrapper(version, fn)
    monkeypatch.setattr(mod, 'MIGRATIONS', wrapped)

    profile = mod._empty_profile('u_chain')
    profile['profile_version'] = '0.1.0'

    migrated = mod.migrate_profile(profile)

    assert migrated['profile_version'] == mod.CURRENT_PROFILE_VERSION
    for version, count in call_counts.items():
        assert count == 1, f'{version} was called {count} times, expected 1'


# ===========================================================================
# T005: マイグレーションの再実行
# ===========================================================================

def test_t005_migrating_twice_does_not_duplicate_or_bump_count():
    fixture = _load_fixture(FIXTURE_013)

    once = mod.migrate_profile(deepcopy(fixture))
    twice = mod.migrate_profile(deepcopy(once))

    assert once['profile_update_count'] == twice['profile_update_count'] == fixture['profile_update_count']
    assert once['summary']['stable_candidates'] == twice['summary']['stable_candidates']
    assert len(twice['summary']['stable_candidates']) == len(fixture['summary']['stable_candidates'])


# ===========================================================================
# T006: 不正なJSON
# ===========================================================================

def test_t006_invalid_json_raises_and_leaves_original_untouched(monkeypatch, tmp_path):
    _use_tmp_profiles_dir(monkeypatch, tmp_path)
    path = tmp_path / 'u_broken.json'
    path.write_text('{not valid json', encoding='utf-8')

    with pytest.raises(mod.ProfileLoadError):
        mod.load_user_profile('u_broken')

    assert path.read_text(encoding='utf-8') == '{not valid json'
    assert not any(p.suffix == '.bak' for p in tmp_path.iterdir())
    assert list(tmp_path.iterdir()) == [path]


# ===========================================================================
# T007: 未対応バージョン
# ===========================================================================

def test_t007_unsupported_version_raises_and_leaves_original_untouched(monkeypatch, tmp_path):
    _use_tmp_profiles_dir(monkeypatch, tmp_path)
    profile = mod._empty_profile('u_future')
    profile['profile_version'] = '9.9.9'
    path = tmp_path / 'u_future.json'
    _write_profile(path, profile)
    before = path.read_text(encoding='utf-8')

    with pytest.raises(mod.UnsupportedProfileVersionError):
        mod.load_user_profile('u_future')

    assert path.read_text(encoding='utf-8') == before


# ===========================================================================
# T008: 保存途中の失敗
# ===========================================================================

def test_t008_atomic_save_failure_keeps_original(tmp_path):
    path = tmp_path / 'u_atomic.json'
    original = mod._empty_profile('u_atomic')
    original['profile_version'] = mod.CURRENT_PROFILE_VERSION
    _write_profile(path, original)

    broken = mod._empty_profile('u_atomic')
    broken['profile_version'] = mod.CURRENT_PROFILE_VERSION
    broken['values'] = 'not-a-list'  # fails validate_profile inside atomic_save_profile

    with pytest.raises(Exception):
        mod.atomic_save_profile(path, broken)

    saved_back = json.loads(path.read_text(encoding='utf-8'))
    assert saved_back == original


# ===========================================================================
# T009: プロフィールリセットからの復旧
# ===========================================================================

def test_t009_recover_reset_profile_target1_update_9_to_10():
    old = mod.migrate_profile(_load_fixture(FIXTURE_012))
    reset = _load_fixture(FIXTURES_DIR / 'reset_after_v012.json')
    session_id = next(e for e in reset['evidence'] if e not in old['evidence'])

    recovered = mod.recover_reset_profile(old, reset, session_id)

    assert recovered['profile_update_count'] == 10
    assert recovered['first_created_at'] == old['first_created_at']
    for old_session in old['evidence']:
        assert old_session in recovered['evidence']
    assert session_id in recovered['evidence']

    # old plain-text personality_traits must not be silently replaced by only this
    # session's candidate text (regression check for the legacy-stub-seeding fix)
    old_fixture = _load_fixture(FIXTURE_012)
    for field in ['communication_style', 'decision_style', 'emotional_tendency']:
        assert old_fixture['personality_traits'][field] in recovered['personality_traits'][field]

    # old flat conversation_topics must survive alongside the new ones
    old_topics = set(old_fixture['preferences']['conversation_topics'])
    recovered_topics = set(recovered['preferences']['conversation_topics'])
    assert old_topics.issubset(recovered_topics)


def test_t009_recover_reset_profile_target2_update_10_to_11():
    old = mod.migrate_profile(_load_fixture(FIXTURE_013))
    reset = _load_fixture(FIXTURES_DIR / 'reset_after_v013.json')
    session_id = next(e for e in reset['evidence'] if e not in old['evidence'])

    recovered = mod.recover_reset_profile(old, reset, session_id)

    assert recovered['profile_update_count'] == 11
    assert recovered['first_created_at'] == old['first_created_at']
    assert session_id in recovered['evidence']
    assert len(recovered['evidence']) == 10  # existing 10-evidence cap, oldest naturally evicted


# ===========================================================================
# T010 / T011: user_id と first_created_at の維持
# ===========================================================================

def test_t010_user_id_preserved_across_migration():
    fixture = _load_fixture(FIXTURE_012)
    migrated = mod.migrate_profile(fixture)
    assert migrated['user_id'] == fixture['user_id']


def test_t011_first_created_at_preserved_across_migration():
    fixture = _load_fixture(FIXTURE_013)
    migrated = mod.migrate_profile(fixture)
    assert migrated['first_created_at'] == fixture['first_created_at']


# ===========================================================================
# T012: 旧バージョンの全フィールド維持
# ===========================================================================

def test_t012_all_legacy_fields_preserved():
    fixture = _load_fixture(FIXTURE_012)
    migrated = mod.migrate_profile(fixture)

    assert migrated['values'] == fixture['values']
    assert migrated['preferences']['conversation_topics'] == fixture['preferences']['conversation_topics']
    assert migrated['preferences']['dislikes'] == fixture['preferences']['dislikes']
    assert migrated['summary']['stable'] == fixture['summary']['stable']
    assert migrated['summary']['recent'] == fixture['summary']['recent']
    assert migrated['summary']['growth'] == fixture['summary']['growth']
    assert migrated['summary']['tensions'] == fixture['summary']['tensions']
    assert migrated['personality_traits'] == fixture['personality_traits']
    assert migrated['matching_hypothesis']['reasoning_history'] == fixture['matching_hypothesis']['reasoning_history']
    assert migrated['matching_hypothesis']['stable_good_match'] == fixture['matching_hypothesis']['stable_good_match']
    assert migrated['evidence'] == fixture['evidence']
    assert migrated['confidence'] == fixture['confidence']
