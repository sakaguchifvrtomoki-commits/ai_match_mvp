import 'package:fairies_app/models/match_response.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> matchJson({
  bool profileUpdated = true,
  bool includeSupport = true,
}) => {
  'analysis': {
    'personality': '穏やか',
    'values': '誠実さ',
    'hidden_needs': '安心感',
    'communication_style': '丁寧',
    'ideal_partner_type': '対話できる人',
    'summary': '穏やかで誠実な人です',
  },
  'match': {
    'matched_candidate': {
      'id': 'c01',
      'name': 'あおい',
      'age': 29,
      'personality': '明るい',
      'values': '信頼',
      'hobbies': '読書',
      'communication_style': '率直',
      'relationship_style': '協力的',
      'description': '相性のよい候補者',
    },
    'match_score': 85,
    'match_label': '好相性',
    'match_reason': '価値観が近い',
    'possible_concern': '会話の速度差',
    'recommended_first_message': '好きな本を教えてください',
  },
  'top_candidates': [
    {
      'candidate': {
        'id': 'c01',
        'name': 'あおい',
        'age': 29,
        'personality': '明るい',
        'values': '信頼',
        'hobbies': '読書',
        'communication_style': '率直',
        'relationship_style': '協力的',
        'description': '相性のよい候補者',
      },
      'similarity': 0.85,
    },
  ],
  'after_match_support': includeSupport
      ? {
          'first_message_today': '挨拶から始めましょう',
          'question_in_3days': '最近読んだ本は？',
          'avoid_phrase': '決めつける表現',
          'slow_reply_action': '少し待つ',
        }
      : null,
  'profile_updated': profileUpdated,
};

void main() {
  test('parses analysis, match, candidates and support', () {
    final response = MatchResponse.fromJson(matchJson());

    expect(response.analysis.summary, '穏やかで誠実な人です');
    expect(response.analysis.hiddenNeeds, '安心感');
    expect(response.match.matchedCandidate.name, 'あおい');
    expect(response.match.matchedCandidate.age, 29);
    expect(response.match.matchScore, 85);
    expect(response.topCandidates.single.similarity, 0.85);
    expect(response.afterMatchSupport?.questionIn3days, '最近読んだ本は？');
    expect(response.profileUpdated, isTrue);
  });

  test('accepts null support and a failed profile update', () {
    final response = MatchResponse.fromJson(
      matchJson(profileUpdated: false, includeSupport: false),
    );

    expect(response.afterMatchSupport, isNull);
    expect(response.profileUpdated, isFalse);
    expect(response.match.matchedCandidate.id, 'c01');
  });

  test('normalizes nullable analysis text without displaying null values', () {
    final json = matchJson();
    final analysis = Map<String, dynamic>.from(
      json['analysis'] as Map<String, dynamic>,
    );
    json['analysis'] = analysis;
    analysis['personality'] = null;
    analysis['values'] = '';

    final response = MatchResponse.fromJson(json);

    expect(response.analysis.personality, isEmpty);
    expect(response.analysis.values, isEmpty);
    expect(response.analysis.hiddenNeeds, '安心感');
  });

  test('parses optional fairy profile summary and accepts a missing field', () {
    final withSummary = matchJson();
    withSummary['fairy_profile_summary'] = {
      'understanding': '長期的な理解',
      'values': ['信頼', '対話'],
      'relationship_style': 'じっくり',
      'good_match': '誠実な相手',
    };

    final parsed = MatchResponse.fromJson(withSummary);
    final legacy = MatchResponse.fromJson(matchJson());

    expect(parsed.fairyProfileSummary?.understanding, '長期的な理解');
    expect(parsed.fairyProfileSummary?.values, ['信頼', '対話']);
    expect(parsed.fairyProfileSummary?.relationshipStyle, 'じっくり');
    expect(parsed.fairyProfileSummary?.goodMatch, '誠実な相手');
    expect(legacy.fairyProfileSummary, isNull);
  });
}
