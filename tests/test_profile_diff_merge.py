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
    assert merged['personality_traits']['communication_style'] == '丁寧'
    assert '価値2' in merged['values']
    assert 'topic2' in merged['preferences']['conversation_topics']
    assert 's1' in merged['evidence']
    assert merged['profile_update_count'] == 2
