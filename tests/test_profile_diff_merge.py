import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('app', Path(__file__).resolve().parents[1] / 'app.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_merge_user_profiles_accepts_diff_payload():
    existing = {
        'user_id': 'u1',
        'summary': {'stable': 'A', 'recent': '', 'growth': '', 'tensions': ['x']},
        'personality_traits': {'communication_style': '', 'decision_style': '', 'emotional_tendency': ''},
        'values': ['価値1'],
        'preferences': {'relationship_style': '', 'conversation_topics': ['topic1'], 'dislikes': ['d1']},
        'matching_hypothesis': {'stable_good_match': '', 'recent_good_match': '', 'likely_bad_match': '', 'reasoning_history': ['r1']},
        'confidence': {'summary': 0.2, 'values': 0.2, 'matching_hypothesis': 0.2},
        'memory_notes': [], 'uncertainties': [], 'evidence': ['e1'],
        'profile_update_count': 1,
        'first_created_at': '2024-01-01'
    }
    diff = {
        'summary': {'stable_candidate': 'A2', 'recent': '新しい傾向', 'growth': '成長', 'new_tensions': ['t2']},
        'personality_traits_updates': {'communication_style': '丁寧', 'decision_style': '', 'emotional_tendency': ''},
        'new_values': ['価値2'],
        'preference_updates': {'relationship_style': 'ゆっくり', 'new_conversation_topics': ['topic2'], 'new_dislikes': ['d2']},
        'matching_hypothesis_updates': {'stable_good_match_candidate': '相性良し', 'recent_good_match': '最近も良し', 'likely_bad_match': '', 'new_reasons': ['理由']},
        'confidence': {'summary': 0.8, 'values': 0.7, 'matching_hypothesis': 0.6}
    }

    merged = mod.merge_user_profiles(existing, diff, 's1')

    assert merged['summary']['recent'] == '新しい傾向'
    assert merged['summary']['stable_candidates'][0]['description'] == 'A2'
    assert merged['personality_traits']['communication_style'] == '丁寧'
    assert '価値2' in merged['values']
    assert 'topic2' in merged['preferences']['conversation_topics']
    assert 's1' in merged['evidence']
    assert merged['profile_update_count'] == 2


def test_merge_user_profiles_preserves_existing_stable_when_candidate_unconfirmed():
    existing = {
        'user_id': 'u2',
        'summary': {'stable': '既存の安定性', 'recent': '', 'growth': '', 'tensions': [], 'stable_candidates': []},
        'personality_traits': {'communication_style': '', 'decision_style': '', 'emotional_tendency': ''},
        'values': [],
        'preferences': {'relationship_style': '', 'conversation_topics': [], 'dislikes': []},
        'matching_hypothesis': {'stable_good_match': '', 'recent_good_match': '', 'likely_bad_match': '', 'reasoning_history': []},
        'confidence': {'summary': 0.2, 'values': 0.2, 'matching_hypothesis': 0.2},
        'memory_notes': [], 'uncertainties': [], 'evidence': [],
        'profile_update_count': 1,
        'first_created_at': '2024-01-01'
    }
    diff = {
        'summary': {'stable_candidate': '新しい候補', 'recent': '', 'growth': '', 'new_tensions': []},
        'personality_traits_updates': {},
        'new_values': [],
        'preference_updates': {},
        'matching_hypothesis_updates': {},
        'confidence': {'summary': 0.5, 'values': 0.0, 'matching_hypothesis': 0.0}
    }

    merged = mod.merge_user_profiles(existing, diff, 's2')

    assert merged['summary']['stable'] == '既存の安定性'
    assert merged['summary']['stable_candidates'][0]['description'] == '新しい候補'
    assert merged['summary']['stable_candidates'][0]['status'] == 'candidate'


def test_initial_session_keeps_summary_stable_empty_and_recent_populated():
    existing = mod._empty_profile('u3')
    diff = {
        'summary': {'stable_candidate': '短く鋭い表現を好む', 'recent': '今回の会話で短く鋭い表現を好むと分かった', 'growth': '', 'new_tensions': []},
        'personality_traits_updates': {'communication_style': '簡潔に話す'},
        'new_values': [],
        'preference_updates': {'new_conversation_topics': ['さくらみこ']},
        'matching_hypothesis_updates': {'recent_good_match': '落ち着いた雰囲気の人', 'new_reasons': ['この人は安心感がある']},
        'confidence': {'summary': 0.6, 'values': 0.4, 'matching_hypothesis': 0.5}
    }

    merged = mod.merge_user_profiles(existing, diff, 's3')

    assert merged['summary']['stable'] == ''
    assert merged['summary']['recent'] == '今回の会話で短く鋭い表現を好むと分かった'
    assert merged['summary']['stable_candidates'][0]['support_count'] == 1
    assert merged['matching_hypothesis']['recent_good_match'] == '落ち着いた雰囲気の人'
    assert merged['preferences']['conversation_topics'][0] == 'さくらみこ'


def test_same_candidate_merges_across_sessions_and_promotes_stable():
    existing = {
        'user_id': 'u4',
        'summary': {'stable': '', 'recent': '', 'growth': '', 'tensions': [], 'stable_candidates': [{'canonical_key': 'prefers_sharp_short', 'description': '短く鋭い表現を好む', 'status': 'candidate', 'support_count': 1, 'first_seen_session_id': 's1', 'last_seen_session_id': 's1', 'evidence': ['s1'], 'confidence': 0.4}]},
        'personality_traits': {'communication_style': '', 'decision_style': '', 'emotional_tendency': ''},
        'values': [],
        'preferences': {'relationship_style': '', 'conversation_topics': [], 'dislikes': []},
        'matching_hypothesis': {'stable_good_match': '', 'recent_good_match': '', 'likely_bad_match': '', 'reasoning_history': []},
        'confidence': {'summary': 0.2, 'values': 0.2, 'matching_hypothesis': 0.2},
        'memory_notes': [], 'uncertainties': [], 'evidence': ['s1'],
        'profile_update_count': 1,
        'first_created_at': '2024-01-01'
    }
    diff = {
        'summary': {'stable_candidates': [{'canonical_key': 'prefers_sharp_short', 'description': '一言で刺さる、キレ味のある表現に惹かれる'}], 'recent': '同じ傾向を再確認', 'growth': '', 'new_tensions': []},
        'personality_traits_updates': {},
        'new_values': [],
        'preference_updates': {},
        'matching_hypothesis_updates': {},
        'confidence': {'summary': 0.6, 'values': 0.0, 'matching_hypothesis': 0.0}
    }

    merged = mod.merge_user_profiles(existing, diff, 's2')

    assert merged['summary']['stable_candidates'][0]['support_count'] == 2
    assert 's2' in merged['summary']['stable_candidates'][0]['evidence']
    assert merged['summary']['stable'] == '短く鋭い表現を好む'


def test_explicit_correction_invalidates_old_candidate_and_prioritizes_new():
    existing = {
        'user_id': 'u5',
        'summary': {'stable': '短く鋭い表現を好む', 'recent': '', 'growth': '', 'tensions': [], 'stable_candidates': [{'description': '短く鋭い表現を好む', 'status': 'stable', 'support_count': 2, 'first_seen_session_id': 's1', 'last_seen_session_id': 's1', 'evidence': ['s1'], 'confidence': 0.7}]},
        'personality_traits': {'communication_style': '短く鋭い', 'decision_style': '', 'emotional_tendency': ''},
        'values': [],
        'preferences': {'relationship_style': '', 'conversation_topics': [], 'dislikes': []},
        'matching_hypothesis': {'stable_good_match': '', 'recent_good_match': '', 'likely_bad_match': '', 'reasoning_history': []},
        'confidence': {'summary': 0.2, 'values': 0.2, 'matching_hypothesis': 0.2},
        'memory_notes': [], 'uncertainties': [], 'evidence': ['s1'],
        'profile_update_count': 1,
        'first_created_at': '2024-01-01'
    }
    diff = {
        'summary': {'stable_candidate': 'ゆっくり丁寧な説明を好む', 'recent': '実はゆっくり丁寧に説明してほしい', 'growth': '', 'new_tensions': []},
        'personality_traits_updates': {'communication_style': 'ゆっくり丁寧に説明する'},
        'new_values': [],
        'preference_updates': {},
        'matching_hypothesis_updates': {},
        'confidence': {'summary': 0.7, 'values': 0.0, 'matching_hypothesis': 0.0},
        'corrections': [{'field': 'summary', 'old_value': '短く鋭い表現を好む', 'new_value': 'ゆっくり丁寧な説明を好む'}]
    }

    merged = mod.merge_user_profiles(existing, diff, 's2')

    assert merged['summary']['stable'] == 'ゆっくり丁寧な説明を好む'
    assert merged['summary']['stable_candidates'][0]['status'] == 'corrected'
    assert merged['personality_traits']['communication_style'] == 'ゆっくり丁寧に説明する'
    assert 's2' in merged['summary']['stable_candidates'][0]['evidence']


def test_topics_over_limit_keep_new_topic_and_prioritize_reappearing_items():
    existing = {
        'user_id': 'u6',
        'summary': {'stable': '', 'recent': '', 'growth': '', 'tensions': [], 'stable_candidates': []},
        'personality_traits': {'communication_style': '', 'decision_style': '', 'emotional_tendency': ''},
        'values': [],
        'preferences': {'relationship_style': '', 'conversation_topics': [f'topic{i}' for i in range(30)], 'dislikes': []},
        'matching_hypothesis': {'stable_good_match': '', 'recent_good_match': '', 'likely_bad_match': '', 'reasoning_history': []},
        'confidence': {'summary': 0.2, 'values': 0.2, 'matching_hypothesis': 0.2},
        'memory_notes': [], 'uncertainties': [], 'evidence': [],
        'profile_update_count': 1,
        'first_created_at': '2024-01-01'
    }
    diff = {
        'summary': {'stable_candidate': '', 'recent': '', 'growth': '', 'new_tensions': []},
        'personality_traits_updates': {},
        'new_values': [],
        'preference_updates': {'new_conversation_topics': ['新規重要トピック']},
        'matching_hypothesis_updates': {},
        'confidence': {'summary': 0.0, 'values': 0.0, 'matching_hypothesis': 0.0}
    }

    merged = mod.merge_user_profiles(existing, diff, 's4')

    assert '新規重要トピック' in merged['preferences']['conversation_topics']
    assert len(merged['preferences']['conversation_topics']) == 30


# ===========================================================================
# Helper factories
# ===========================================================================

def _min_diff(**overrides):
    """Minimal valid diff-payload. Keyword overrides replace top-level keys."""
    d = {
        'summary': {'stable_candidates': [], 'recent': '', 'growth': '', 'new_tensions': []},
        'personality_traits_updates': {},
        'personality_trait_candidates': {'communication_style': [], 'decision_style': [], 'emotional_tendency': []},
        'new_values': [],
        'preference_updates': {'relationship_style': '', 'new_conversation_topics': [], 'new_dislikes': []},
        'matching_hypothesis_updates': {'stable_good_match_candidates': [], 'recent_good_match': '', 'likely_bad_match': '', 'new_reasons': []},
        'corrections': [],
        'confidence': {'summary': 0.0, 'values': 0.0, 'matching_hypothesis': 0.0},
    }
    d.update(overrides)
    return d


# ===========================================================================
# 初回と昇格
# ===========================================================================

def test_first_profile_created_with_valid_structure():
    merged = mod.merge_user_profiles(mod._empty_profile('u_fp1'), _min_diff(), 's_fp1')
    assert 'summary' in merged
    assert merged['profile_update_count'] == 1


def test_first_summary_stable_is_empty_after_one_session():
    diff = _min_diff(summary={'stable_candidates': [{'canonical_key': 'ck_x', 'description': 'X特徴'}], 'recent': '最近の傾向', 'growth': '', 'new_tensions': []})
    merged = mod.merge_user_profiles(mod._empty_profile('u_fp2'), diff, 's_fp2')
    assert merged['summary']['stable'] == ''
    assert merged['summary']['recent'] == '最近の傾向'


def test_first_candidate_has_support_count_1():
    diff = _min_diff(
        summary={'stable_candidates': [{'canonical_key': 'prefers_short', 'description': '短い表現を好む'}], 'recent': '', 'growth': '', 'new_tensions': []},
        confidence={'summary': 0.5, 'values': 0.0, 'matching_hypothesis': 0.0},
    )
    merged = mod.merge_user_profiles(mod._empty_profile('u_fp3'), diff, 's_fp3')
    cands = merged['summary']['stable_candidates']
    assert len(cands) == 1
    assert cands[0]['support_count'] == 1
    assert cands[0]['status'] == 'candidate'
    assert cands[0]['canonical_key'] == 'prefers_short'


def test_different_session_same_canonical_key_increments_support_count():
    diff1 = _min_diff(
        summary={'stable_candidates': [{'canonical_key': 'prefers_short', 'description': '短い表現を好む'}], 'recent': '', 'growth': '', 'new_tensions': []},
        confidence={'summary': 0.5, 'values': 0.0, 'matching_hypothesis': 0.0},
    )
    after1 = mod.merge_user_profiles(mod._empty_profile('u_fp4'), diff1, 's_fp4a')
    diff2 = _min_diff(
        summary={'stable_candidates': [{'canonical_key': 'prefers_short', 'description': '短い表現が好き'}], 'recent': '', 'growth': '', 'new_tensions': []},
        confidence={'summary': 0.6, 'values': 0.0, 'matching_hypothesis': 0.0},
    )
    after2 = mod.merge_user_profiles(after1, diff2, 's_fp4b')
    cands = after2['summary']['stable_candidates']
    assert len(cands) == 1
    assert cands[0]['support_count'] == 2


def test_support_count_2_promotes_to_stable():
    diff1 = _min_diff(
        summary={'stable_candidates': [{'canonical_key': 'prefers_short', 'description': '短い表現を好む'}], 'recent': '', 'growth': '', 'new_tensions': []},
        confidence={'summary': 0.5, 'values': 0.0, 'matching_hypothesis': 0.0},
    )
    after1 = mod.merge_user_profiles(mod._empty_profile('u_fp5'), diff1, 's_fp5a')
    diff2 = _min_diff(
        summary={'stable_candidates': [{'canonical_key': 'prefers_short', 'description': '短い表現を好む'}], 'recent': '', 'growth': '', 'new_tensions': []},
        confidence={'summary': 0.6, 'values': 0.0, 'matching_hypothesis': 0.0},
    )
    after2 = mod.merge_user_profiles(after1, diff2, 's_fp5b')
    cands = after2['summary']['stable_candidates']
    assert cands[0]['status'] == 'stable'
    assert after2['summary']['stable'] == '短い表現を好む'


def test_same_session_reapply_does_not_increment_support_count():
    diff = _min_diff(
        summary={'stable_candidates': [{'canonical_key': 'prefers_short', 'description': '短い表現を好む'}], 'recent': '', 'growth': '', 'new_tensions': []},
        confidence={'summary': 0.5, 'values': 0.0, 'matching_hypothesis': 0.0},
    )
    after1 = mod.merge_user_profiles(mod._empty_profile('u_fp6'), diff, 's_fp6')
    assert after1['summary']['stable_candidates'][0]['support_count'] == 1
    after2 = mod.merge_user_profiles(after1, diff, 's_fp6')  # same session_id
    assert after2['summary']['stable_candidates'][0]['support_count'] == 1


def test_profile_update_count_same_session_no_increment():
    diff = _min_diff(summary={'stable_candidates': [], 'recent': '今回の傾向', 'growth': '', 'new_tensions': []})
    after1 = mod.merge_user_profiles(mod._empty_profile('u_fp7'), diff, 's_fp7')
    assert after1['profile_update_count'] == 1
    after2 = mod.merge_user_profiles(after1, diff, 's_fp7')  # same session
    assert after2['profile_update_count'] == 1


# ===========================================================================
# 複数candidate
# ===========================================================================

def test_two_independent_candidates_in_one_session():
    diff = _min_diff(summary={'stable_candidates': [
        {'canonical_key': 'prefers_sharp', 'description': '短く鋭い表現を好む'},
        {'canonical_key': 'prefers_detailed_self', 'description': '自分で話すときは丁寧に説明する'},
    ], 'recent': '', 'growth': '', 'new_tensions': []})
    merged = mod.merge_user_profiles(mod._empty_profile('u_mc1'), diff, 's_mc1')
    cands = merged['summary']['stable_candidates']
    assert len(cands) == 2
    keys = [c['canonical_key'] for c in cands]
    assert 'prefers_sharp' in keys
    assert 'prefers_detailed_self' in keys


def test_only_confirmed_candidate_increments_support_count():
    diff1 = _min_diff(summary={'stable_candidates': [
        {'canonical_key': 'ck_a', 'description': 'A特徴'},
        {'canonical_key': 'ck_b', 'description': 'B特徴'},
    ], 'recent': '', 'growth': '', 'new_tensions': []})
    after1 = mod.merge_user_profiles(mod._empty_profile('u_mc2'), diff1, 's_mc2a')
    diff2 = _min_diff(summary={'stable_candidates': [
        {'canonical_key': 'ck_a', 'description': 'A特徴（確認）'},
    ], 'recent': '', 'growth': '', 'new_tensions': []})
    after2 = mod.merge_user_profiles(after1, diff2, 's_mc2b')
    by_key = {c['canonical_key']: c for c in after2['summary']['stable_candidates']}
    assert by_key['ck_a']['support_count'] == 2
    assert by_key['ck_b']['support_count'] == 1


def test_unrelated_candidates_not_merged():
    diff = _min_diff(summary={'stable_candidates': [
        {'canonical_key': 'likes_cats', 'description': '猫が好き'},
        {'canonical_key': 'likes_dogs', 'description': '犬が好き'},
    ], 'recent': '', 'growth': '', 'new_tensions': []})
    merged = mod.merge_user_profiles(mod._empty_profile('u_mc3'), diff, 's_mc3')
    assert len(merged['summary']['stable_candidates']) == 2


def test_opposite_candidates_not_merged():
    diff = _min_diff(summary={'stable_candidates': [
        {'canonical_key': 'prefers_short', 'description': '短く鋭い表現を好む'},
        {'canonical_key': 'prefers_long', 'description': 'ゆっくり丁寧な説明を好む'},
    ], 'recent': '', 'growth': '', 'new_tensions': []})
    merged = mod.merge_user_profiles(mod._empty_profile('u_mc4'), diff, 's_mc4')
    assert len(merged['summary']['stable_candidates']) == 2
    keys = [c['canonical_key'] for c in merged['summary']['stable_candidates']]
    assert 'prefers_short' in keys
    assert 'prefers_long' in keys


def test_common_word_only_does_not_merge_different_canonical_keys():
    existing = mod._empty_profile('u_mc5')
    existing['summary']['stable_candidates'] = [{
        'canonical_key': 'likes_sharp_expression', 'description': '鋭い表現を好む',
        'status': 'candidate', 'support_count': 1,
        'first_seen_session_id': 's1', 'last_seen_session_id': 's1',
        'evidence': ['s1'], 'confidence': 0.5,
    }]
    existing['evidence'] = ['s1']
    diff = _min_diff(summary={'stable_candidates': [
        {'canonical_key': 'likes_gentle_explanation', 'description': '丁寧な説明を好む'},
    ], 'recent': '', 'growth': '', 'new_tensions': []})
    merged = mod.merge_user_profiles(existing, diff, 's2')
    assert len(merged['summary']['stable_candidates']) == 2


# ===========================================================================
# 明示的訂正
# ===========================================================================

def test_corrections_schema_with_canonical_key_processed():
    existing = mod._empty_profile('u_ec1')
    existing['summary']['stable_candidates'] = [{
        'canonical_key': 'prefers_sharp', 'description': '短く鋭い表現を好む',
        'status': 'stable', 'support_count': 2,
        'first_seen_session_id': 's1', 'last_seen_session_id': 's1',
        'evidence': ['s1'], 'confidence': 0.7,
    }]
    existing['evidence'] = ['s1']
    diff = _min_diff(
        summary={'stable_candidates': [{'canonical_key': 'prefers_gentle', 'description': 'ゆっくり丁寧な説明を好む'}], 'recent': '', 'growth': '', 'new_tensions': []},
        corrections=[{
            'field': 'summary.stable',
            'target_canonical_key': 'prefers_sharp',
            'old_value': '短く鋭い表現を好む',
            'new_canonical_key': 'prefers_gentle',
            'new_value': 'ゆっくり丁寧な説明を好む',
            'reason': 'ユーザーが明示的に訂正した',
        }],
        confidence={'summary': 0.7, 'values': 0.0, 'matching_hypothesis': 0.0},
    )
    merged = mod.merge_user_profiles(existing, diff, 's_ec1')
    by_key = {c['canonical_key']: c for c in merged['summary']['stable_candidates']}
    assert 'prefers_sharp' in by_key
    assert by_key['prefers_sharp']['status'] == 'corrected'


def test_target_canonical_key_old_candidate_becomes_corrected():
    existing = mod._empty_profile('u_ec2')
    existing['summary']['stable_candidates'] = [{
        'canonical_key': 'old_trait', 'description': '古い特徴',
        'status': 'stable', 'support_count': 2,
        'first_seen_session_id': 's1', 'last_seen_session_id': 's1',
        'evidence': ['s1'], 'confidence': 0.7,
    }]
    existing['evidence'] = ['s1']
    diff = _min_diff(corrections=[{
        'field': 'summary.stable',
        'target_canonical_key': 'old_trait',
        'old_value': '古い特徴',
        'new_canonical_key': 'new_trait',
        'new_value': '新しい特徴',
        'reason': '訂正',
    }])
    merged = mod.merge_user_profiles(existing, diff, 's_ec2')
    by_key = {c['canonical_key']: c for c in merged['summary']['stable_candidates']}
    assert by_key['old_trait']['status'] == 'corrected'


def test_new_candidate_created_separate_object_from_old():
    existing = mod._empty_profile('u_ec3')
    existing['summary']['stable_candidates'] = [{
        'canonical_key': 'old_trait', 'description': '古い特徴',
        'status': 'stable', 'support_count': 2,
        'first_seen_session_id': 's1', 'last_seen_session_id': 's1',
        'evidence': ['s1'], 'confidence': 0.7,
    }]
    existing['evidence'] = ['s1']
    diff = _min_diff(corrections=[{
        'field': 'summary.stable',
        'target_canonical_key': 'old_trait',
        'old_value': '古い特徴',
        'new_canonical_key': 'new_trait',
        'new_value': '新しい特徴',
        'reason': '訂正',
    }])
    merged = mod.merge_user_profiles(existing, diff, 's_ec3')
    cands = merged['summary']['stable_candidates']
    assert len(cands) == 2
    old_c = next(c for c in cands if c['canonical_key'] == 'old_trait')
    new_c = next(c for c in cands if c['canonical_key'] == 'new_trait')
    assert old_c is not new_c


def test_summary_stable_updated_to_correction_value():
    existing = mod._empty_profile('u_ec4')
    existing['summary']['stable_candidates'] = [{
        'canonical_key': 'old_trait', 'description': '古い特徴',
        'status': 'stable', 'support_count': 2,
        'first_seen_session_id': 's1', 'last_seen_session_id': 's1',
        'evidence': ['s1'], 'confidence': 0.7,
    }]
    existing['evidence'] = ['s1']
    diff = _min_diff(corrections=[{
        'field': 'summary.stable',
        'target_canonical_key': 'old_trait',
        'old_value': '古い特徴',
        'new_canonical_key': 'new_trait',
        'new_value': '新しい特徴',
        'reason': '訂正',
    }])
    merged = mod.merge_user_profiles(existing, diff, 's_ec4')
    assert merged['summary']['stable'] == '新しい特徴'


def test_old_and_new_correction_candidates_are_different_objects():
    existing = mod._empty_profile('u_ec5')
    existing['summary']['stable_candidates'] = [{
        'canonical_key': 'old_key', 'description': '旧特徴',
        'status': 'stable', 'support_count': 2,
        'first_seen_session_id': 's1', 'last_seen_session_id': 's1',
        'evidence': ['s1'], 'confidence': 0.7,
    }]
    existing['evidence'] = ['s1']
    diff = _min_diff(corrections=[{
        'field': 'summary.stable', 'target_canonical_key': 'old_key',
        'old_value': '旧特徴', 'new_canonical_key': 'new_key', 'new_value': '新特徴', 'reason': '訂正',
    }])
    merged = mod.merge_user_profiles(existing, diff, 's_ec5')
    cands = merged['summary']['stable_candidates']
    old_c = next((c for c in cands if c.get('canonical_key') == 'old_key'), None)
    new_c = next((c for c in cands if c.get('canonical_key') == 'new_key'), None)
    assert old_c is not None
    assert new_c is not None
    assert old_c is not new_c


def test_correction_session_tracked_in_both_candidates():
    existing = mod._empty_profile('u_ec6')
    existing['summary']['stable_candidates'] = [{
        'canonical_key': 'old_key', 'description': '旧特徴',
        'status': 'stable', 'support_count': 2,
        'first_seen_session_id': 's1', 'last_seen_session_id': 's1',
        'evidence': ['s1'], 'confidence': 0.7,
    }]
    existing['evidence'] = ['s1']
    diff = _min_diff(corrections=[{
        'field': 'summary.stable', 'target_canonical_key': 'old_key',
        'old_value': '旧特徴', 'new_canonical_key': 'new_key', 'new_value': '新特徴', 'reason': '訂正',
    }])
    merged = mod.merge_user_profiles(existing, diff, 's_ec6_corr')
    cands = merged['summary']['stable_candidates']
    old_c = next(c for c in cands if c.get('canonical_key') == 'old_key')
    new_c = next(c for c in cands if c.get('canonical_key') == 'new_key')
    assert 's_ec6_corr' in old_c.get('evidence', [])
    assert 's_ec6_corr' in new_c.get('evidence', [])


def test_non_mention_does_not_trigger_correction():
    existing = mod._empty_profile('u_ec7')
    existing['summary']['stable_candidates'] = [{
        'canonical_key': 'prefers_short', 'description': '短い表現を好む',
        'status': 'candidate', 'support_count': 1,
        'first_seen_session_id': 's1', 'last_seen_session_id': 's1',
        'evidence': ['s1'], 'confidence': 0.5,
    }]
    existing['evidence'] = ['s1']
    diff = _min_diff(summary={'stable_candidates': [], 'recent': '別の話題', 'growth': '', 'new_tensions': []})
    merged = mod.merge_user_profiles(existing, diff, 's_ec7')
    cands = merged['summary']['stable_candidates']
    assert len(cands) == 1
    assert cands[0]['status'] == 'candidate'


def test_single_opposite_opinion_without_corrections_key_not_correction():
    existing = mod._empty_profile('u_ec8')
    existing['summary']['stable_candidates'] = [{
        'canonical_key': 'prefers_short', 'description': '短い表現を好む',
        'status': 'stable', 'support_count': 2,
        'first_seen_session_id': 's1', 'last_seen_session_id': 's1',
        'evidence': ['s1'], 'confidence': 0.7,
    }]
    existing['evidence'] = ['s1']
    diff = _min_diff(
        summary={'stable_candidates': [{'canonical_key': 'prefers_long', 'description': 'ゆっくり丁寧な説明を好む'}], 'recent': '', 'growth': '', 'new_tensions': []},
    )
    merged = mod.merge_user_profiles(existing, diff, 's_ec8')
    cands = merged['summary']['stable_candidates']
    old_c = next((c for c in cands if c.get('canonical_key') == 'prefers_short'), None)
    assert old_c is not None
    assert old_c['status'] in ('stable', 'candidate')


# ===========================================================================
# stable_good_match
# ===========================================================================

def test_first_session_only_recent_good_match_updated():
    diff = _min_diff(matching_hypothesis_updates={
        'stable_good_match_candidates': [],
        'recent_good_match': '落ち着いた雰囲気の人',
        'likely_bad_match': '', 'new_reasons': [],
    })
    merged = mod.merge_user_profiles(mod._empty_profile('u_sgm1'), diff, 's_sgm1')
    assert merged['matching_hypothesis']['recent_good_match'] == '落ち着いた雰囲気の人'
    assert merged['matching_hypothesis']['stable_good_match'] == ''


def test_stable_good_match_unchanged_after_one_session_with_new_candidate():
    diff = _min_diff(
        matching_hypothesis_updates={
            'stable_good_match_candidates': [{'canonical_key': 'gentle_listener', 'description': 'やさしく聞いてくれる人'}],
            'recent_good_match': 'やさしく聞いてくれる人', 'likely_bad_match': '', 'new_reasons': [],
        },
        confidence={'summary': 0.0, 'values': 0.0, 'matching_hypothesis': 0.6},
    )
    merged = mod.merge_user_profiles(mod._empty_profile('u_sgm2'), diff, 's_sgm2')
    assert merged['matching_hypothesis']['stable_good_match'] == ''
    cands = merged['matching_hypothesis']['stable_candidates']
    assert len(cands) == 1
    assert cands[0]['support_count'] == 1


def test_same_canonical_key_two_sessions_promotes_stable_good_match():
    diff1 = _min_diff(
        matching_hypothesis_updates={
            'stable_good_match_candidates': [{'canonical_key': 'gentle_listener', 'description': 'やさしく聞いてくれる人'}],
            'recent_good_match': '', 'likely_bad_match': '', 'new_reasons': [],
        },
        confidence={'summary': 0.0, 'values': 0.0, 'matching_hypothesis': 0.6},
    )
    after1 = mod.merge_user_profiles(mod._empty_profile('u_sgm3'), diff1, 's_sgm3a')
    diff2 = _min_diff(
        matching_hypothesis_updates={
            'stable_good_match_candidates': [{'canonical_key': 'gentle_listener', 'description': 'ゆっくり丁寧に会話できる人'}],
            'recent_good_match': '', 'likely_bad_match': '', 'new_reasons': [],
        },
        confidence={'summary': 0.0, 'values': 0.0, 'matching_hypothesis': 0.7},
    )
    after2 = mod.merge_user_profiles(after1, diff2, 's_sgm3b')
    assert after2['matching_hypothesis']['stable_good_match'] != ''
    cands = after2['matching_hypothesis']['stable_candidates']
    the_cand = next((c for c in cands if c.get('canonical_key') == 'gentle_listener'), None)
    assert the_cand is not None
    assert the_cand['support_count'] == 2
    assert the_cand['status'] == 'stable'


def test_different_description_same_canonical_key_promotes_stable_good_match():
    diff1 = _min_diff(
        matching_hypothesis_updates={
            'stable_good_match_candidates': [{'canonical_key': 'patient_talker', 'description': '落ち着いて丁寧に話せる相手'}],
            'recent_good_match': '', 'likely_bad_match': '', 'new_reasons': [],
        },
        confidence={'summary': 0.0, 'values': 0.0, 'matching_hypothesis': 0.6},
    )
    after1 = mod.merge_user_profiles(mod._empty_profile('u_sgm4'), diff1, 's_sgm4a')
    diff2 = _min_diff(
        matching_hypothesis_updates={
            'stable_good_match_candidates': [{'canonical_key': 'patient_talker', 'description': 'ゆっくり丁寧に会話できる人'}],
            'recent_good_match': '', 'likely_bad_match': '', 'new_reasons': [],
        },
        confidence={'summary': 0.0, 'values': 0.0, 'matching_hypothesis': 0.7},
    )
    after2 = mod.merge_user_profiles(after1, diff2, 's_sgm4b')
    assert after2['matching_hypothesis']['stable_good_match'] != ''


def test_existing_stable_good_match_not_cleared_by_one_new_candidate():
    existing = mod._empty_profile('u_sgm5')
    existing['matching_hypothesis']['stable_good_match'] = '落ち着いた人'
    existing['matching_hypothesis']['stable_candidates'] = [{
        'canonical_key': 'calm_person', 'description': '落ち着いた人',
        'status': 'stable', 'support_count': 2,
        'first_seen_session_id': 's1', 'last_seen_session_id': 's2',
        'evidence': ['s1', 's2'], 'confidence': 0.7,
    }]
    existing['evidence'] = ['s1', 's2']
    diff = _min_diff(
        matching_hypothesis_updates={
            'stable_good_match_candidates': [{'canonical_key': 'energetic_person', 'description': '元気な人'}],
            'recent_good_match': '元気な人', 'likely_bad_match': '', 'new_reasons': [],
        },
        confidence={'summary': 0.0, 'values': 0.0, 'matching_hypothesis': 0.5},
    )
    merged = mod.merge_user_profiles(existing, diff, 's_sgm5')
    assert merged['matching_hypothesis']['stable_good_match'] == '落ち着いた人'


def test_explicit_correction_updates_stable_good_match():
    existing = mod._empty_profile('u_sgm6')
    existing['matching_hypothesis']['stable_good_match'] = '落ち着いた人'
    existing['matching_hypothesis']['stable_candidates'] = [{
        'canonical_key': 'calm_person', 'description': '落ち着いた人',
        'status': 'stable', 'support_count': 2,
        'first_seen_session_id': 's1', 'last_seen_session_id': 's2',
        'evidence': ['s1', 's2'], 'confidence': 0.7,
    }]
    existing['evidence'] = ['s1', 's2']
    diff = _min_diff(corrections=[{
        'field': 'matching_hypothesis.stable_good_match',
        'target_canonical_key': 'calm_person',
        'old_value': '落ち着いた人',
        'new_canonical_key': 'funny_person',
        'new_value': '笑いをわかってくれる人',
        'reason': '訂正',
    }])
    merged = mod.merge_user_profiles(existing, diff, 's_sgm6')
    by_key = {c['canonical_key']: c for c in merged['matching_hypothesis']['stable_candidates']}
    assert by_key['calm_person']['status'] == 'corrected'
    assert merged['matching_hypothesis']['stable_good_match'] == '笑いをわかってくれる人'


# ===========================================================================
# personality_traits candidates
# ===========================================================================

def test_two_non_contradictory_traits_both_preserved_in_candidates():
    diff = _min_diff(personality_trait_candidates={
        'communication_style': [
            {'canonical_key': 'prefers_detail', 'description': '丁寧に詳しく説明する'},
            {'canonical_key': 'listens_carefully', 'description': '相手の話をよく聞く'},
        ],
        'decision_style': [], 'emotional_tendency': [],
    })
    merged = mod.merge_user_profiles(mod._empty_profile('u_pt1'), diff, 's_pt1')
    cands = merged['personality_trait_candidates']['communication_style']
    assert len(cands) == 2


def test_same_canonical_key_trait_support_count_increases():
    diff1 = _min_diff(personality_trait_candidates={'communication_style': [{'canonical_key': 'prefers_detail', 'description': '丁寧に説明する'}], 'decision_style': [], 'emotional_tendency': []})
    after1 = mod.merge_user_profiles(mod._empty_profile('u_pt2'), diff1, 's_pt2a')
    diff2 = _min_diff(personality_trait_candidates={'communication_style': [{'canonical_key': 'prefers_detail', 'description': '丁寧に詳しく説明する'}], 'decision_style': [], 'emotional_tendency': []})
    after2 = mod.merge_user_profiles(after1, diff2, 's_pt2b')
    by_key = {c['canonical_key']: c for c in after2['personality_trait_candidates']['communication_style']}
    assert by_key['prefers_detail']['support_count'] == 2


def test_unrelated_traits_not_merged_in_candidates():
    diff = _min_diff(personality_trait_candidates={
        'communication_style': [
            {'canonical_key': 'direct_speaker', 'description': '直接的に話す'},
            {'canonical_key': 'humorous_speaker', 'description': 'ユーモアを交えて話す'},
        ],
        'decision_style': [], 'emotional_tendency': [],
    })
    merged = mod.merge_user_profiles(mod._empty_profile('u_pt3'), diff, 's_pt3')
    assert len(merged['personality_trait_candidates']['communication_style']) == 2


def test_correction_invalidates_target_trait_candidate():
    existing = mod._empty_profile('u_pt4')
    existing['personality_trait_candidates'] = {
        'communication_style': [{
            'canonical_key': 'direct_speaker', 'description': '直接的に話す',
            'status': 'stable', 'support_count': 2,
            'first_seen_session_id': 's1', 'last_seen_session_id': 's1',
            'evidence': ['s1'], 'confidence': 0.7,
        }],
        'decision_style': [], 'emotional_tendency': [],
    }
    existing['evidence'] = ['s1']
    diff = _min_diff(corrections=[{
        'field': 'personality_traits.communication_style',
        'target_canonical_key': 'direct_speaker',
        'old_value': '直接的に話す',
        'new_canonical_key': 'gentle_speaker',
        'new_value': 'やわらかく話す',
        'reason': '訂正',
    }])
    merged = mod.merge_user_profiles(existing, diff, 's_pt4')
    by_key = {c['canonical_key']: c for c in merged['personality_trait_candidates']['communication_style']}
    assert by_key['direct_speaker']['status'] == 'corrected'
    assert 'gentle_speaker' in by_key


def test_personality_trait_display_under_200_chars():
    diff = _min_diff(personality_trait_candidates={
        'communication_style': [
            {'canonical_key': f'ck_{i}', 'description': f'特徴{i}です。これは長い説明文です。' * 5}
            for i in range(5)
        ],
        'decision_style': [], 'emotional_tendency': [],
    })
    merged = mod.merge_user_profiles(mod._empty_profile('u_pt5'), diff, 's_pt5')
    assert len(merged['personality_traits']['communication_style']) <= 200


def test_existing_trait_not_removed_on_non_mention():
    existing = mod._empty_profile('u_pt6')
    existing['personality_trait_candidates'] = {
        'communication_style': [{
            'canonical_key': 'detail_oriented', 'description': '丁寧',
            'status': 'candidate', 'support_count': 1,
            'first_seen_session_id': 's1', 'last_seen_session_id': 's1',
            'evidence': ['s1'], 'confidence': 0.5,
        }],
        'decision_style': [], 'emotional_tendency': [],
    }
    existing['evidence'] = ['s1']
    diff = _min_diff(personality_trait_candidates={'communication_style': [], 'decision_style': [], 'emotional_tendency': []})
    merged = mod.merge_user_profiles(existing, diff, 's_pt6')
    cands = merged['personality_trait_candidates']['communication_style']
    assert len(cands) == 1
    assert cands[0]['canonical_key'] == 'detail_oriented'


# ===========================================================================
# conversation_topics metadata
# ===========================================================================

def test_topics_with_metadata_over_limit_new_important_topic_saved():
    existing = mod._empty_profile('u_ct1')
    existing['preferences']['conversation_topic_metadata'] = [{
        'canonical_key': f'topic_{i}', 'display_name': f'topic{i}',
        'support_count': 1, 'first_seen_session_id': 's0', 'last_seen_session_id': 's0',
        'evidence': ['s0'], 'importance': 1,
    } for i in range(30)]
    existing['preferences']['conversation_topics'] = [f'topic{i}' for i in range(30)]
    existing['evidence'] = ['s0']
    diff = _min_diff(preference_updates={'relationship_style': '', 'new_conversation_topics': [{'canonical_key': 'new_important', 'description': '新しい重要トピック'}], 'new_dislikes': []})
    merged = mod.merge_user_profiles(existing, diff, 's_ct1')
    assert '新しい重要トピック' in merged['preferences']['conversation_topics']
    assert len(merged['preferences']['conversation_topics']) == 30


def test_lowest_priority_topic_evicted_when_over_limit():
    existing = mod._empty_profile('u_ct2')
    existing['preferences']['conversation_topic_metadata'] = [{
        'canonical_key': f'low_{i}', 'display_name': f'低優先{i}',
        'support_count': 1, 'first_seen_session_id': 's0', 'last_seen_session_id': 's0',
        'evidence': ['s0'], 'importance': 1,
    } for i in range(30)]
    existing['preferences']['conversation_topics'] = [f'低優先{i}' for i in range(30)]
    existing['evidence'] = ['s0']
    diff = _min_diff(preference_updates={'relationship_style': '', 'new_conversation_topics': [{'canonical_key': 'high_prio', 'description': '高優先トピック'}], 'new_dislikes': []})
    merged = mod.merge_user_profiles(existing, diff, 's_ct2')
    assert '高優先トピック' in merged['preferences']['conversation_topics']
    assert len(merged['preferences']['conversation_topics']) == 30
    low_topics = [t for t in merged['preferences']['conversation_topics'] if t.startswith('低優先')]
    assert len(low_topics) == 29


def test_reappeared_topic_support_count_increases():
    existing = mod._empty_profile('u_ct3')
    existing['preferences']['conversation_topic_metadata'] = [{
        'canonical_key': 'cats', 'display_name': '猫',
        'support_count': 1, 'first_seen_session_id': 's1', 'last_seen_session_id': 's1',
        'evidence': ['s1'], 'importance': 2,
    }]
    existing['preferences']['conversation_topics'] = ['猫']
    existing['evidence'] = ['s1']
    diff = _min_diff(preference_updates={'relationship_style': '', 'new_conversation_topics': [{'canonical_key': 'cats', 'description': '猫'}], 'new_dislikes': []})
    merged = mod.merge_user_profiles(existing, diff, 's_ct3')
    cats_meta = next((m for m in merged['preferences']['conversation_topic_metadata'] if m.get('canonical_key') == 'cats'), None)
    assert cats_meta is not None
    assert cats_meta['support_count'] == 2


def test_same_session_topic_support_count_not_incremented_idempotent():
    existing = mod._empty_profile('u_ct4')
    existing['preferences']['conversation_topic_metadata'] = [{
        'canonical_key': 'cats', 'display_name': '猫',
        'support_count': 1, 'first_seen_session_id': 's1', 'last_seen_session_id': 's1',
        'evidence': ['s1'], 'importance': 2,
    }]
    existing['preferences']['conversation_topics'] = ['猫']
    existing['evidence'] = ['s1']
    diff = _min_diff(preference_updates={'relationship_style': '', 'new_conversation_topics': [{'canonical_key': 'cats', 'description': '猫'}], 'new_dislikes': []})
    merged1 = mod.merge_user_profiles(existing, diff, 's2_ct4')
    merged2 = mod.merge_user_profiles(merged1, diff, 's2_ct4')  # same session
    meta1 = next(m for m in merged1['preferences']['conversation_topic_metadata'] if m.get('canonical_key') == 'cats')
    meta2 = next(m for m in merged2['preferences']['conversation_topic_metadata'] if m.get('canonical_key') == 'cats')
    assert meta1['support_count'] == meta2['support_count']


def test_topic_metadata_saved_to_profile():
    diff = _min_diff(preference_updates={'relationship_style': '', 'new_conversation_topics': [{'canonical_key': 'anime', 'description': 'アニメ'}], 'new_dislikes': []})
    merged = mod.merge_user_profiles(mod._empty_profile('u_ct5'), diff, 's_ct5')
    meta = merged['preferences']['conversation_topic_metadata']
    assert len(meta) == 1
    assert meta[0]['canonical_key'] == 'anime'
    assert meta[0]['display_name'] == 'アニメ'
    assert meta[0]['support_count'] == 1


def test_topic_metadata_carried_to_next_merge():
    diff1 = _min_diff(preference_updates={'relationship_style': '', 'new_conversation_topics': [{'canonical_key': 'anime', 'description': 'アニメ'}], 'new_dislikes': []})
    after1 = mod.merge_user_profiles(mod._empty_profile('u_ct6'), diff1, 's_ct6a')
    diff2 = _min_diff(preference_updates={'relationship_style': '', 'new_conversation_topics': [{'canonical_key': 'games', 'description': 'ゲーム'}], 'new_dislikes': []})
    after2 = mod.merge_user_profiles(after1, diff2, 's_ct6b')
    meta_keys = [m.get('canonical_key') for m in after2['preferences']['conversation_topic_metadata']]
    assert 'anime' in meta_keys
    assert 'games' in meta_keys


def test_same_canonical_key_topic_not_duplicated_in_metadata():
    diff1 = _min_diff(preference_updates={'relationship_style': '', 'new_conversation_topics': [{'canonical_key': 'music', 'description': '音楽'}], 'new_dislikes': []})
    after1 = mod.merge_user_profiles(mod._empty_profile('u_ct7'), diff1, 's_ct7a')
    diff2 = _min_diff(preference_updates={'relationship_style': '', 'new_conversation_topics': [{'canonical_key': 'music', 'description': '音楽（好き）'}], 'new_dislikes': []})
    after2 = mod.merge_user_profiles(after1, diff2, 's_ct7b')
    music_entries = [m for m in after2['preferences']['conversation_topic_metadata'] if m.get('canonical_key') == 'music']
    assert len(music_entries) == 1


# ===========================================================================
# reasoning_history entries
# ===========================================================================

def test_new_reasoning_entry_saved():
    diff = _min_diff(matching_hypothesis_updates={
        'stable_good_match_candidates': [], 'recent_good_match': '', 'likely_bad_match': '',
        'new_reasons': [{'text': '笑いを共有できると感じた', 'session_id': 's_rh1'}],
    })
    merged = mod.merge_user_profiles(mod._empty_profile('u_rh1'), diff, 's_rh1')
    entries = merged['matching_hypothesis']['reasoning_history_entries']
    assert len(entries) == 1
    assert entries[0]['text'] == '笑いを共有できると感じた'


def test_full_reasoning_history_keeps_newest_entry():
    existing = mod._empty_profile('u_rh2')
    # Newest-first: index 0 = most recent prior entry
    existing['matching_hypothesis']['reasoning_history_entries'] = [
        {'text': f'根拠{19-i}', 'session_id': f's_old{19-i}', 'created_at': '2024-01-01T00:00:00'}
        for i in range(20)
    ]
    existing['evidence'] = ['s_old0']
    diff = _min_diff(matching_hypothesis_updates={
        'stable_good_match_candidates': [], 'recent_good_match': '', 'likely_bad_match': '',
        'new_reasons': [{'text': '最新の根拠', 'session_id': 's_rh2_new'}],
    })
    merged = mod.merge_user_profiles(existing, diff, 's_rh2_new')
    entries = merged['matching_hypothesis']['reasoning_history_entries']
    assert len(entries) == 20
    texts = [e['text'] for e in entries]
    assert '最新の根拠' in texts


def test_oldest_reasoning_entry_dropped_when_full():
    existing = mod._empty_profile('u_rh3')
    # Newest-first: 根拠19 = most recent, 根拠0 = oldest
    existing['matching_hypothesis']['reasoning_history_entries'] = [
        {'text': f'根拠{19-i}', 'session_id': f's_old{19-i}', 'created_at': f'2024-01-{(19-i+1):02d}T00:00:00'}
        for i in range(20)
    ]
    existing['evidence'] = ['s_old0']
    diff = _min_diff(matching_hypothesis_updates={
        'stable_good_match_candidates': [], 'recent_good_match': '', 'likely_bad_match': '',
        'new_reasons': [{'text': '最新の根拠', 'session_id': 's_rh3_new'}],
    })
    merged = mod.merge_user_profiles(existing, diff, 's_rh3_new')
    entries = merged['matching_hypothesis']['reasoning_history_entries']
    texts = [e['text'] for e in entries]
    assert '最新の根拠' in texts
    assert len(entries) == 20
    assert '根拠0' not in texts  # oldest dropped


def test_reasoning_history_tracks_session_id():
    diff = _min_diff(matching_hypothesis_updates={
        'stable_good_match_candidates': [], 'recent_good_match': '', 'likely_bad_match': '',
        'new_reasons': [{'text': '根拠テキスト', 'session_id': 's_rh4_tracked'}],
    })
    merged = mod.merge_user_profiles(mod._empty_profile('u_rh4'), diff, 's_rh4_tracked')
    entries = merged['matching_hypothesis']['reasoning_history_entries']
    assert entries[0]['session_id'] == 's_rh4_tracked'


def test_same_session_reasoning_not_duplicated():
    diff = _min_diff(matching_hypothesis_updates={
        'stable_good_match_candidates': [], 'recent_good_match': '', 'likely_bad_match': '',
        'new_reasons': [{'text': '根拠テキスト', 'session_id': 's_rh5'}],
    })
    after1 = mod.merge_user_profiles(mod._empty_profile('u_rh5'), diff, 's_rh5')
    after2 = mod.merge_user_profiles(after1, diff, 's_rh5')  # same session = idempotent
    entries = after2['matching_hypothesis']['reasoning_history_entries']
    matching = [e for e in entries if e['text'] == '根拠テキスト']
    assert len(matching) == 1


# ===========================================================================
# evidence と安全性
# ===========================================================================

def test_evidence_keeps_newest_10():
    existing = mod._empty_profile('u_ev1')
    existing['evidence'] = [f's_old{i}' for i in range(9)]
    merged = mod.merge_user_profiles(existing, _min_diff(), 's_new')
    assert 's_new' in merged['evidence']
    assert len(merged['evidence']) == 10


def test_11th_evidence_drops_oldest():
    existing = mod._empty_profile('u_ev2')
    existing['evidence'] = [f's{i}' for i in range(10)]
    merged = mod.merge_user_profiles(existing, _min_diff(), 's_newest')
    assert 's_newest' in merged['evidence']
    assert 's0' not in merged['evidence']
    assert len(merged['evidence']) == 10


def test_same_session_evidence_not_duplicated():
    existing = mod._empty_profile('u_ev3')
    existing['evidence'] = ['s1', 's2']
    merged = mod.merge_user_profiles(existing, _min_diff(), 's3')
    second = mod.merge_user_profiles(merged, _min_diff(), 's3')
    assert second['evidence'].count('s3') == 1


def test_empty_diff_does_not_clear_existing_values():
    existing = mod._empty_profile('u_ev4')
    existing['summary']['recent'] = '既存の傾向'
    existing['values'] = ['価値観A']
    merged = mod.merge_user_profiles(existing, _min_diff(), 's_ev4')
    assert merged['values'] == ['価値観A']


def test_v012_summary_without_stable_candidates_normalized():
    old_summary = {'stable': '既存の安定特徴', 'recent': '', 'growth': '', 'tensions': []}
    normalized = mod.normalize_summary(old_summary)
    assert 'stable_candidates' in normalized
    assert isinstance(normalized['stable_candidates'], list)
    assert normalized['stable'] == '既存の安定特徴'


def test_v012_matching_hypothesis_normalized_with_new_fields():
    old_mh = {
        'stable_good_match': '落ち着いた人', 'recent_good_match': '',
        'likely_bad_match': '', 'reasoning_history': ['過去の根拠'],
    }
    normalized_mh = mod.normalize_matching_hypothesis(old_mh)
    assert 'stable_candidates' in normalized_mh
    assert 'reasoning_history_entries' in normalized_mh
    assert isinstance(normalized_mh['reasoning_history_entries'], list)


def test_old_profile_without_metadata_merges_safely():
    old_profile = {
        'user_id': 'u_old1',
        'summary': {'stable': '昔の特徴', 'recent': '', 'growth': '', 'tensions': []},
        'personality_traits': {'communication_style': '話し好き', 'decision_style': '', 'emotional_tendency': ''},
        'values': [],
        'preferences': {'relationship_style': '', 'conversation_topics': ['ゲーム'], 'dislikes': []},
        'matching_hypothesis': {'stable_good_match': '', 'recent_good_match': '', 'likely_bad_match': '', 'reasoning_history': []},
        'confidence': {'summary': 0.2, 'values': 0.0, 'matching_hypothesis': 0.0},
        'memory_notes': [], 'uncertainties': [], 'evidence': [],
        'profile_update_count': 1, 'first_created_at': '2024-01-01',
    }
    diff = _min_diff(preference_updates={'relationship_style': '', 'new_conversation_topics': [{'canonical_key': 'music', 'description': '音楽'}], 'new_dislikes': []})
    merged = mod.merge_user_profiles(old_profile, diff, 's_old_merge')
    assert isinstance(merged['preferences']['conversation_topic_metadata'], list)
    assert isinstance(merged.get('personality_trait_candidates', {}).get('communication_style', []), list)
    assert '音楽' in merged['preferences']['conversation_topics']
    assert 'ゲーム' in merged['preferences']['conversation_topics']


# ===========================================================================
# reinforcement — summary
# ===========================================================================

def _profile_with_summary_candidate(user_id, canonical_key, description, support_count=1, status='candidate', evidence=None):
    evidence = evidence or ['session_1']
    p = mod._empty_profile(user_id)
    p['summary']['stable_candidates'] = [{
        'canonical_key': canonical_key,
        'description': description,
        'status': status,
        'support_count': support_count,
        'first_seen_session_id': evidence[0],
        'last_seen_session_id': evidence[-1],
        'evidence': list(evidence),
        'confidence': 0.5,
    }]
    p['evidence'] = list(evidence)
    return p


def test_reinforce_existing_candidate_by_key():
    existing = _profile_with_summary_candidate('u_ri1', 'prefers_deep_conversations_over_small_talk', '表面的な雑談よりも深く話すほうが好き')
    diff = _min_diff(summary={
        'stable_candidates': [],
        'reinforced_candidate_keys': ['prefers_deep_conversations_over_small_talk'],
        'recent': '本質的な話を重視する傾向を再確認した', 'growth': '', 'new_tensions': [],
    })
    merged = mod.merge_user_profiles(existing, diff, 'session_2')
    cand = merged['summary']['stable_candidates'][0]
    assert cand['support_count'] == 2


def test_reinforce_increments_support_count_from_1_to_2():
    existing = _profile_with_summary_candidate('u_ri2', 'ck_x', '特徴X')
    diff = _min_diff(summary={'stable_candidates': [], 'reinforced_candidate_keys': ['ck_x'], 'recent': '', 'growth': '', 'new_tensions': []})
    merged = mod.merge_user_profiles(existing, diff, 's_ri2b')
    assert merged['summary']['stable_candidates'][0]['support_count'] == 2


def test_reinforce_adds_second_session_to_evidence():
    existing = _profile_with_summary_candidate('u_ri3', 'ck_y', '特徴Y')
    diff = _min_diff(summary={'stable_candidates': [], 'reinforced_candidate_keys': ['ck_y'], 'recent': '', 'growth': '', 'new_tensions': []})
    merged = mod.merge_user_profiles(existing, diff, 'session_2')
    cand = merged['summary']['stable_candidates'][0]
    assert 'session_1' in cand['evidence']
    assert 'session_2' in cand['evidence']


def test_reinforce_updates_last_seen_session_id():
    existing = _profile_with_summary_candidate('u_ri4', 'ck_z', '特徴Z')
    diff = _min_diff(summary={'stable_candidates': [], 'reinforced_candidate_keys': ['ck_z'], 'recent': '', 'growth': '', 'new_tensions': []})
    merged = mod.merge_user_profiles(existing, diff, 'session_new')
    assert merged['summary']['stable_candidates'][0]['last_seen_session_id'] == 'session_new'


def test_reinforce_promotes_status_to_stable():
    existing = _profile_with_summary_candidate('u_ri5', 'ck_p', '特徴P', support_count=1, status='candidate')
    diff = _min_diff(summary={'stable_candidates': [], 'reinforced_candidate_keys': ['ck_p'], 'recent': '', 'growth': '', 'new_tensions': []})
    merged = mod.merge_user_profiles(existing, diff, 's_ri5b')
    assert merged['summary']['stable_candidates'][0]['status'] == 'stable'


def test_reinforce_updates_summary_stable_text_using_existing_description():
    existing = _profile_with_summary_candidate('u_ri6', 'ck_q', '既存の説明文')
    diff = _min_diff(summary={'stable_candidates': [], 'reinforced_candidate_keys': ['ck_q'], 'recent': '別の言い換え', 'growth': '', 'new_tensions': []})
    merged = mod.merge_user_profiles(existing, diff, 's_ri6b')
    assert merged['summary']['stable'] == '既存の説明文'


def test_reinforce_does_not_use_recent_text_for_stable():
    existing = _profile_with_summary_candidate('u_ri7', 'ck_r', '保存済みの特徴説明')
    diff = _min_diff(summary={'stable_candidates': [], 'reinforced_candidate_keys': ['ck_r'], 'recent': '今回AIが生成した言い換え文', 'growth': '', 'new_tensions': []})
    merged = mod.merge_user_profiles(existing, diff, 's_ri7b')
    assert merged['summary']['stable'] == '保存済みの特徴説明'
    assert merged['summary']['stable'] != '今回AIが生成した言い換え文'


def test_reinforce_same_session_does_not_increment_support_count():
    existing = _profile_with_summary_candidate('u_ri8', 'ck_s', '特徴S')
    diff = _min_diff(summary={'stable_candidates': [], 'reinforced_candidate_keys': ['ck_s'], 'recent': '', 'growth': '', 'new_tensions': []})
    after1 = mod.merge_user_profiles(existing, diff, 'session_2')
    after2 = mod.merge_user_profiles(after1, diff, 'session_2')  # same session
    assert after2['summary']['stable_candidates'][0]['support_count'] == 2


def test_reinforce_nonexistent_key_does_not_create_new_candidate():
    existing = _profile_with_summary_candidate('u_ri9', 'existing_key', '既存特徴')
    diff = _min_diff(summary={'stable_candidates': [], 'reinforced_candidate_keys': ['nonexistent_key'], 'recent': '', 'growth': '', 'new_tensions': []})
    merged = mod.merge_user_profiles(existing, diff, 's_ri9b')
    keys = [c['canonical_key'] for c in merged['summary']['stable_candidates']]
    assert 'nonexistent_key' not in keys
    assert len(merged['summary']['stable_candidates']) == 1


def test_reinforce_corrected_candidate_does_not_increment():
    existing = _profile_with_summary_candidate('u_ri10', 'ck_corrected', '訂正済み特徴', status='corrected')
    diff = _min_diff(summary={'stable_candidates': [], 'reinforced_candidate_keys': ['ck_corrected'], 'recent': '', 'growth': '', 'new_tensions': []})
    merged = mod.merge_user_profiles(existing, diff, 's_ri10b')
    cand = merged['summary']['stable_candidates'][0]
    assert cand['status'] == 'corrected'
    assert cand['support_count'] == 1


def test_reinforce_empty_list_does_not_change_existing_profile():
    existing = _profile_with_summary_candidate('u_ri11', 'ck_t', '特徴T')
    diff = _min_diff(summary={'stable_candidates': [], 'reinforced_candidate_keys': [], 'recent': '', 'growth': '', 'new_tensions': []})
    merged = mod.merge_user_profiles(existing, diff, 's_ri11b')
    assert merged['summary']['stable_candidates'][0]['support_count'] == 1


def test_reinforce_multiple_keys_simultaneously():
    existing = mod._empty_profile('u_ri12')
    existing['summary']['stable_candidates'] = [
        {'canonical_key': 'ck_a', 'description': '特徴A', 'status': 'candidate', 'support_count': 1,
         'first_seen_session_id': 's1', 'last_seen_session_id': 's1', 'evidence': ['s1'], 'confidence': 0.5},
        {'canonical_key': 'ck_b', 'description': '特徴B', 'status': 'candidate', 'support_count': 1,
         'first_seen_session_id': 's1', 'last_seen_session_id': 's1', 'evidence': ['s1'], 'confidence': 0.5},
    ]
    existing['evidence'] = ['s1']
    diff = _min_diff(summary={'stable_candidates': [], 'reinforced_candidate_keys': ['ck_a', 'ck_b'], 'recent': '', 'growth': '', 'new_tensions': []})
    merged = mod.merge_user_profiles(existing, diff, 's2')
    by_key = {c['canonical_key']: c for c in merged['summary']['stable_candidates']}
    assert by_key['ck_a']['support_count'] == 2
    assert by_key['ck_b']['support_count'] == 2


# ===========================================================================
# reinforcement — new candidate vs re-confirmation 区別
# ===========================================================================

def test_new_candidate_created_from_stable_candidates_not_reinforcement():
    existing = mod._empty_profile('u_rd1')
    existing['evidence'] = []
    diff = _min_diff(summary={
        'stable_candidates': [{'canonical_key': 'brand_new_key', 'description': '全く新しい特徴'}],
        'reinforced_candidate_keys': [],
        'recent': '', 'growth': '', 'new_tensions': [],
    })
    merged = mod.merge_user_profiles(existing, diff, 's_rd1')
    keys = [c['canonical_key'] for c in merged['summary']['stable_candidates']]
    assert 'brand_new_key' in keys
    assert merged['summary']['stable_candidates'][0]['support_count'] == 1


def test_reinforcement_does_not_duplicate_existing_candidate():
    existing = _profile_with_summary_candidate('u_rd2', 'ck_existing', '既存特徴')
    diff = _min_diff(summary={
        'stable_candidates': [],
        'reinforced_candidate_keys': ['ck_existing'],
        'recent': '', 'growth': '', 'new_tensions': [],
    })
    merged = mod.merge_user_profiles(existing, diff, 's_rd2b')
    same_key = [c for c in merged['summary']['stable_candidates'] if c['canonical_key'] == 'ck_existing']
    assert len(same_key) == 1


def test_new_candidate_and_reinforcement_same_session():
    existing = _profile_with_summary_candidate('u_rd3', 'ck_old', '古い特徴')
    diff = _min_diff(summary={
        'stable_candidates': [{'canonical_key': 'ck_new', 'description': '新しい特徴'}],
        'reinforced_candidate_keys': ['ck_old'],
        'recent': '', 'growth': '', 'new_tensions': [],
    })
    merged = mod.merge_user_profiles(existing, diff, 's_rd3b')
    by_key = {c['canonical_key']: c for c in merged['summary']['stable_candidates']}
    assert by_key['ck_old']['support_count'] == 2
    assert by_key['ck_new']['support_count'] == 1


def test_unrelated_existing_candidate_not_reinforced():
    existing = mod._empty_profile('u_rd4')
    existing['summary']['stable_candidates'] = [
        {'canonical_key': 'ck_a', 'description': '特徴A', 'status': 'candidate', 'support_count': 1,
         'first_seen_session_id': 's1', 'last_seen_session_id': 's1', 'evidence': ['s1'], 'confidence': 0.5},
        {'canonical_key': 'ck_b', 'description': '特徴B', 'status': 'candidate', 'support_count': 1,
         'first_seen_session_id': 's1', 'last_seen_session_id': 's1', 'evidence': ['s1'], 'confidence': 0.5},
    ]
    existing['evidence'] = ['s1']
    diff = _min_diff(summary={'stable_candidates': [], 'reinforced_candidate_keys': ['ck_a'], 'recent': '', 'growth': '', 'new_tensions': []})
    merged = mod.merge_user_profiles(existing, diff, 's2')
    by_key = {c['canonical_key']: c for c in merged['summary']['stable_candidates']}
    assert by_key['ck_a']['support_count'] == 2
    assert by_key['ck_b']['support_count'] == 1  # unrelated — not incremented


# ===========================================================================
# reinforcement — matching_hypothesis
# ===========================================================================

def _profile_with_mh_candidate(user_id, canonical_key, description, support_count=1, status='candidate', evidence=None):
    evidence = evidence or ['session_1']
    p = mod._empty_profile(user_id)
    p['matching_hypothesis']['stable_candidates'] = [{
        'canonical_key': canonical_key,
        'description': description,
        'status': status,
        'support_count': support_count,
        'first_seen_session_id': evidence[0],
        'last_seen_session_id': evidence[-1],
        'evidence': list(evidence),
        'confidence': 0.5,
    }]
    p['evidence'] = list(evidence)
    return p


def test_mh_reinforce_increments_support_count():
    existing = _profile_with_mh_candidate('u_mhr1', 'gentle_listener', 'やさしく聞いてくれる人')
    diff = _min_diff(matching_hypothesis_updates={
        'stable_good_match_candidates': [],
        'reinforced_stable_good_match_candidate_keys': ['gentle_listener'],
        'recent_good_match': '', 'likely_bad_match': '', 'new_reasons': [],
    })
    merged = mod.merge_user_profiles(existing, diff, 'session_2')
    cand = merged['matching_hypothesis']['stable_candidates'][0]
    assert cand['support_count'] == 2


def test_mh_reinforce_promotes_stable_good_match():
    existing = _profile_with_mh_candidate('u_mhr2', 'patient_talker', '落ち着いて話せる相手')
    diff = _min_diff(matching_hypothesis_updates={
        'stable_good_match_candidates': [],
        'reinforced_stable_good_match_candidate_keys': ['patient_talker'],
        'recent_good_match': '', 'likely_bad_match': '', 'new_reasons': [],
    })
    merged = mod.merge_user_profiles(existing, diff, 'session_2')
    assert merged['matching_hypothesis']['stable_good_match'] == '落ち着いて話せる相手'


def test_mh_reinforce_uses_existing_description_not_new_text():
    existing = _profile_with_mh_candidate('u_mhr3', 'patient_talker', '落ち着いて話せる相手（保存済み）')
    diff = _min_diff(matching_hypothesis_updates={
        'stable_good_match_candidates': [],
        'reinforced_stable_good_match_candidate_keys': ['patient_talker'],
        'recent_good_match': '今回AIが生成した言い換え', 'likely_bad_match': '', 'new_reasons': [],
    })
    merged = mod.merge_user_profiles(existing, diff, 'session_2')
    assert merged['matching_hypothesis']['stable_good_match'] == '落ち着いて話せる相手（保存済み）'


def test_mh_single_new_candidate_does_not_clear_existing_stable_good_match():
    existing = _profile_with_mh_candidate('u_mhr4', 'calm_person', '落ち着いた人', support_count=2, status='stable')
    existing['matching_hypothesis']['stable_good_match'] = '落ち着いた人'
    diff = _min_diff(matching_hypothesis_updates={
        'stable_good_match_candidates': [{'canonical_key': 'new_type', 'description': '違うタイプの人'}],
        'reinforced_stable_good_match_candidate_keys': [],
        'recent_good_match': '', 'likely_bad_match': '', 'new_reasons': [],
    })
    merged = mod.merge_user_profiles(existing, diff, 'session_3')
    assert merged['matching_hypothesis']['stable_good_match'] == '落ち着いた人'


def test_mh_reinforce_same_session_does_not_increment():
    existing = _profile_with_mh_candidate('u_mhr5', 'patient_talker', '落ち着いた相手')
    diff = _min_diff(matching_hypothesis_updates={
        'stable_good_match_candidates': [],
        'reinforced_stable_good_match_candidate_keys': ['patient_talker'],
        'recent_good_match': '', 'likely_bad_match': '', 'new_reasons': [],
    })
    after1 = mod.merge_user_profiles(existing, diff, 'session_2')
    after2 = mod.merge_user_profiles(after1, diff, 'session_2')  # same session
    assert after2['matching_hypothesis']['stable_candidates'][0]['support_count'] == 2


def test_mh_reinforce_nonexistent_key_does_not_create_new_candidate():
    existing = _profile_with_mh_candidate('u_mhr6', 'existing_key', '既存の相手像')
    diff = _min_diff(matching_hypothesis_updates={
        'stable_good_match_candidates': [],
        'reinforced_stable_good_match_candidate_keys': ['made_up_key'],
        'recent_good_match': '', 'likely_bad_match': '', 'new_reasons': [],
    })
    merged = mod.merge_user_profiles(existing, diff, 'session_2')
    keys = [c['canonical_key'] for c in merged['matching_hypothesis']['stable_candidates']]
    assert 'made_up_key' not in keys


# ===========================================================================
# T002 実使用テスト再現
# ===========================================================================

def test_t002_reinforce_deep_conversation_candidate():
    """Reproduction of real usage test T002 — session 2 reinforces a session-1 candidate."""
    existing = mod._empty_profile('u_t002')
    existing['summary']['stable_candidates'] = [{
        'description': '表面的な雑談よりも、考え方や価値観について深く話すほうが好き',
        'canonical_key': 'prefers_deep_conversations_over_small_talk',
        'status': 'candidate',
        'support_count': 1,
        'first_seen_session_id': 'session_1',
        'last_seen_session_id': 'session_1',
        'evidence': ['session_1'],
        'confidence': 0.6,
    }]
    existing['evidence'] = ['session_1']

    diff = {
        'summary': {
            'stable_candidates': [],
            'reinforced_candidate_keys': ['prefers_deep_conversations_over_small_talk'],
            'recent': '本質的な話を重視する傾向を再確認した',
            'growth': '',
            'new_tensions': [],
        },
        'personality_traits_updates': {},
        'personality_trait_candidates': {'communication_style': [], 'decision_style': [], 'emotional_tendency': []},
        'new_values': [],
        'preference_updates': {'relationship_style': '', 'new_conversation_topics': [], 'new_dislikes': []},
        'matching_hypothesis_updates': {'stable_good_match_candidates': [], 'reinforced_stable_good_match_candidate_keys': [], 'recent_good_match': '', 'likely_bad_match': '', 'new_reasons': []},
        'corrections': [],
        'confidence': {'summary': 0.7, 'values': 0.0, 'matching_hypothesis': 0.0},
    }

    merged = mod.merge_user_profiles(existing, diff, 'session_2')

    cand = next(c for c in merged['summary']['stable_candidates'] if c['canonical_key'] == 'prefers_deep_conversations_over_small_talk')
    assert cand['support_count'] == 2, f"Expected support_count=2, got {cand['support_count']}"
    assert cand['status'] == 'stable', f"Expected status=stable, got {cand['status']}"
    assert 'session_1' in cand['evidence']
    assert 'session_2' in cand['evidence']
    assert merged['summary']['stable'] != '', "summary.stable should be non-empty after stable promotion"
    duplicate_keys = [c for c in merged['summary']['stable_candidates'] if c['canonical_key'] == 'prefers_deep_conversations_over_small_talk']
    assert len(duplicate_keys) == 1, "No duplicate candidates should be created"
