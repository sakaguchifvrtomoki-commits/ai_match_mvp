class AnalysisResult {
  const AnalysisResult({
    required this.personality,
    required this.values,
    required this.hiddenNeeds,
    required this.communicationStyle,
    required this.idealPartnerType,
    required this.summary,
  });

  factory AnalysisResult.fromJson(Map<String, dynamic> json) => AnalysisResult(
    personality: _string(json, 'personality'),
    values: _string(json, 'values'),
    hiddenNeeds: _string(json, 'hidden_needs'),
    communicationStyle: _string(json, 'communication_style'),
    idealPartnerType: _string(json, 'ideal_partner_type'),
    summary: _string(json, 'summary'),
  );

  final String personality;
  final String values;
  final String hiddenNeeds;
  final String communicationStyle;
  final String idealPartnerType;
  final String summary;
}

class MatchedCandidate {
  const MatchedCandidate({
    required this.id,
    required this.name,
    required this.age,
    required this.personality,
    required this.values,
    required this.hobbies,
    required this.communicationStyle,
    required this.relationshipStyle,
    required this.description,
  });

  factory MatchedCandidate.fromJson(Map<String, dynamic> json) =>
      MatchedCandidate(
        id: _string(json, 'id'),
        name: _string(json, 'name'),
        age: _integer(json, 'age'),
        personality: _string(json, 'personality'),
        values: _string(json, 'values'),
        hobbies: _string(json, 'hobbies'),
        communicationStyle: _string(json, 'communication_style'),
        relationshipStyle: _string(json, 'relationship_style'),
        description: _string(json, 'description'),
      );

  final String id;
  final String name;
  final int age;
  final String personality;
  final String values;
  final String hobbies;
  final String communicationStyle;
  final String relationshipStyle;
  final String description;
}

class MatchResult {
  const MatchResult({
    required this.matchedCandidate,
    required this.matchScore,
    required this.matchLabel,
    required this.matchReason,
    required this.possibleConcern,
    required this.recommendedFirstMessage,
  });

  factory MatchResult.fromJson(Map<String, dynamic> json) => MatchResult(
    matchedCandidate: MatchedCandidate.fromJson(
      _object(json, 'matched_candidate'),
    ),
    matchScore: _integer(json, 'match_score'),
    matchLabel: _string(json, 'match_label'),
    matchReason: _string(json, 'match_reason'),
    possibleConcern: _string(json, 'possible_concern'),
    recommendedFirstMessage: _string(json, 'recommended_first_message'),
  );

  final MatchedCandidate matchedCandidate;
  final int matchScore;
  final String matchLabel;
  final String matchReason;
  final String possibleConcern;
  final String recommendedFirstMessage;
}

class TopCandidate {
  const TopCandidate({required this.candidate, required this.similarity});

  factory TopCandidate.fromJson(Map<String, dynamic> json) => TopCandidate(
    candidate: MatchedCandidate.fromJson(_object(json, 'candidate')),
    similarity: _number(json, 'similarity').toDouble(),
  );

  final MatchedCandidate candidate;
  final double similarity;
}

class AfterMatchSupport {
  const AfterMatchSupport({
    required this.firstMessageToday,
    required this.questionIn3days,
    required this.avoidPhrase,
    required this.slowReplyAction,
  });

  factory AfterMatchSupport.fromJson(Map<String, dynamic> json) =>
      AfterMatchSupport(
        firstMessageToday: _string(json, 'first_message_today'),
        questionIn3days: _string(json, 'question_in_3days'),
        avoidPhrase: _string(json, 'avoid_phrase'),
        slowReplyAction: _string(json, 'slow_reply_action'),
      );

  final String firstMessageToday;
  final String questionIn3days;
  final String avoidPhrase;
  final String slowReplyAction;
}

class MatchResponse {
  const MatchResponse({
    required this.analysis,
    required this.match,
    required this.topCandidates,
    required this.afterMatchSupport,
    required this.profileUpdated,
  });

  factory MatchResponse.fromJson(Map<String, dynamic> json) {
    final topCandidates = json['top_candidates'];
    final support = json['after_match_support'];
    final profileUpdated = json['profile_updated'];
    if (topCandidates is! List ||
        (support != null && support is! Map<String, dynamic>) ||
        profileUpdated is! bool) {
      throw const FormatException('Invalid match response.');
    }
    return MatchResponse(
      analysis: AnalysisResult.fromJson(_object(json, 'analysis')),
      match: MatchResult.fromJson(_object(json, 'match')),
      topCandidates: topCandidates
          .map((item) {
            if (item is! Map<String, dynamic>) {
              throw const FormatException('Invalid top candidate.');
            }
            return TopCandidate.fromJson(item);
          })
          .toList(growable: false),
      afterMatchSupport: support == null
          ? null
          : AfterMatchSupport.fromJson(support),
      profileUpdated: profileUpdated,
    );
  }

  final AnalysisResult analysis;
  final MatchResult match;
  final List<TopCandidate> topCandidates;
  final AfterMatchSupport? afterMatchSupport;
  final bool profileUpdated;
}

Map<String, dynamic> _object(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! Map<String, dynamic>) {
    throw FormatException('Invalid $key.');
  }
  return value;
}

String _string(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! String) throw FormatException('Invalid $key.');
  return value;
}

num _number(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! num) throw FormatException('Invalid $key.');
  return value;
}

int _integer(Map<String, dynamic> json, String key) {
  final value = _number(json, key);
  if (value != value.roundToDouble()) throw FormatException('Invalid $key.');
  return value.toInt();
}
