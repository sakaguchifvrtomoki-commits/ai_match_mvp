import 'dart:async';
import 'dart:convert';

import 'package:fairies_app/models/chat_message.dart';
import 'package:fairies_app/models/match_response.dart';
import 'package:fairies_app/models/match_loading_phase.dart';
import 'package:fairies_app/services/fairies_api_client.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

http.Response jsonResponse(Map<String, dynamic> body, int statusCode) {
  return http.Response.bytes(
    utf8.encode(jsonEncode(body)),
    statusCode,
    headers: {'content-type': 'application/json; charset=utf-8'},
  );
}

void main() {
  test(
    'POST /sessions sends the required request JSON and parses HTTP 201',
    () async {
      late http.Request captured;
      final client = FairiesApiClient(
        baseUrl: 'http://example.test:8000',
        client: MockClient((request) async {
          captured = request;
          return jsonResponse({
            'user_id': 'user_created',
            'session_id': 'session_created',
            'message': {'role': 'assistant', 'content': 'こんにちは'},
          }, 201);
        }),
      );

      final session = await client.startSession(userId: null, logConsent: true);

      expect(captured.method, 'POST');
      expect(captured.url.toString(), 'http://example.test:8000/sessions');
      expect(jsonDecode(captured.body), {'user_id': null, 'log_consent': true});
      expect(session.userId, 'user_created');
      expect(session.sessionId, 'session_created');
      expect(session.initialMessage.role, 'assistant');
    },
  );

  test('FastAPI common error JSON is parsed separately', () async {
    final client = FairiesApiClient(
      client: MockClient(
        (_) async => jsonResponse({
          'error': {'code': 'INVALID_REQUEST', 'message': 'ログ保存への同意が必要です。'},
        }, 400),
      ),
    );

    expect(
      () => client.startSession(userId: null, logConsent: false),
      throwsA(
        isA<FairiesApiException>()
            .having((error) => error.code, 'code', 'INVALID_REQUEST')
            .having((error) => error.message, 'message', 'ログ保存への同意が必要です。'),
      ),
    );
  });

  test(
    'POST /chat sends the full message history and parses HTTP 200',
    () async {
      late http.Request captured;
      final client = FairiesApiClient(
        baseUrl: 'http://example.test:8000',
        client: MockClient((request) async {
          captured = request;
          return jsonResponse({
            'message': {'role': 'assistant', 'content': 'Fairyの返答'},
          }, 200);
        }),
      );
      const messages = [
        ChatMessage(role: 'assistant', content: '初回挨拶'),
        ChatMessage(role: 'user', content: 'こんにちは'),
      ];

      final reply = await client.sendChat(
        userId: 'user_123',
        sessionId: 'session_456',
        messages: messages,
      );

      expect(captured.method, 'POST');
      expect(captured.url.toString(), 'http://example.test:8000/chat');
      expect(jsonDecode(captured.body), {
        'user_id': 'user_123',
        'session_id': 'session_456',
        'messages': [
          {'role': 'assistant', 'content': '初回挨拶'},
          {'role': 'user', 'content': 'こんにちは'},
        ],
      });
      expect(reply.role, 'assistant');
      expect(reply.content, 'Fairyの返答');
    },
  );

  test('POST /chat parses FastAPI AI errors', () async {
    final client = FairiesApiClient(
      client: MockClient(
        (_) async => jsonResponse({
          'error': {'code': 'AI_RESPONSE_TRUNCATED', 'message': '応答が途中で切れました。'},
        }, 502),
      ),
    );

    expect(
      () => client.sendChat(
        userId: 'user_123',
        sessionId: 'session_456',
        messages: const [ChatMessage(role: 'user', content: 'こんにちは')],
      ),
      throwsA(
        isA<FairiesApiException>().having(
          (error) => error.code,
          'code',
          'AI_RESPONSE_TRUNCATED',
        ),
      ),
    );
  });

  test('POST /match sends the full history and parses HTTP 200', () async {
    late http.Request captured;
    final client = FairiesApiClient(
      baseUrl: 'http://example.test:8000',
      client: MockClient((request) async {
        captured = request;
        return jsonResponse(_matchJson(), 200);
      }),
    );
    const messages = [
      ChatMessage(role: 'assistant', content: '挨拶'),
      ChatMessage(role: 'user', content: '一件目'),
      ChatMessage(role: 'user', content: '二件目'),
      ChatMessage(role: 'user', content: '三件目'),
    ];

    final response = await client.generateMatch(
      userId: 'user_123',
      sessionId: 'session_456',
      messages: messages,
    );

    expect(captured.url.toString(), 'http://example.test:8000/match');
    expect(jsonDecode(captured.body), {
      'user_id': 'user_123',
      'session_id': 'session_456',
      'messages': messages.map((message) => message.toJson()).toList(),
    });
    expect(response.analysis.summary, '分析概要');
    expect(response.match.matchedCandidate.name, 'あおい');
  });

  test('POST /match parses FastAPI errors', () async {
    final client = FairiesApiClient(
      client: MockClient(
        (_) async => jsonResponse({
          'error': {'code': 'MATCHING_FAILED', 'message': 'マッチング失敗'},
        }, 502),
      ),
    );

    expect(
      () => client.generateMatch(
        userId: 'user_123',
        sessionId: 'session_456',
        messages: const [],
      ),
      throwsA(
        isA<FairiesApiException>().having(
          (error) => error.code,
          'code',
          'MATCHING_FAILED',
        ),
      ),
    );
  });

  test('POST /match/stream parses split chunks and multiple lines', () async {
    final payload = [
      jsonEncode({'type': 'progress', 'phase': 'analyzing'}),
      jsonEncode({'type': 'progress', 'phase': 'matching'}),
      jsonEncode({'type': 'progress', 'phase': 'unknown_future_phase'}),
      jsonEncode({'type': 'progress', 'phase': 'memorizing'}),
      jsonEncode({'type': 'result', 'data': _matchJson()}),
      '',
    ].join('\n');
    final splitAt = payload.indexOf('matching') + 3;
    final transport = ChunkedClient([
      utf8.encode(payload.substring(0, splitAt)),
      utf8.encode(payload.substring(splitAt)),
    ]);
    final client = FairiesApiClient(
      baseUrl: 'http://example.test:8000',
      client: transport,
    );
    final phases = <MatchLoadingPhase>[];

    final result = await client.generateMatchStream(
      userId: 'user_123',
      sessionId: 'session_456',
      messages: const [ChatMessage(role: 'user', content: '発言')],
      onProgress: phases.add,
    );

    expect(transport.request?.url.path, '/match/stream');
    expect(jsonDecode(transport.request!.body), {
      'user_id': 'user_123',
      'session_id': 'session_456',
      'messages': [
        {'role': 'user', 'content': '発言'},
      ],
    });
    expect(phases, [
      MatchLoadingPhase.analyzing,
      MatchLoadingPhase.matching,
      MatchLoadingPhase.memorizing,
    ]);
    expect(result.analysis.summary, '分析概要');
  });

  test('POST /match/stream surfaces a terminal error event', () async {
    final client = FairiesApiClient(
      client: ChunkedClient([
        utf8.encode(
          '${jsonEncode({'type': 'progress', 'phase': 'analyzing'})}\n'
          '${jsonEncode({
            'type': 'error',
            'error': {'code': 'ANALYSIS_FAILED', 'message': '分析できませんでした。'},
          })}\n',
        ),
      ]),
    );

    expect(
      () => client.generateMatchStream(
        userId: 'user_123',
        sessionId: 'session_456',
        messages: const [],
        onProgress: (_) {},
      ),
      throwsA(
        isA<FairiesApiException>().having(
          (error) => error.code,
          'code',
          'ANALYSIS_FAILED',
        ),
      ),
    );
  });

  test('malformed match stream does not become a successful result', () async {
    final client = FairiesApiClient(
      client: ChunkedClient([utf8.encode('{not-json}\n')]),
    );

    expect(
      () => client.generateMatchStream(
        userId: 'user_123',
        sessionId: 'session_456',
        messages: const [],
        onProgress: (_) {},
      ),
      throwsA(
        isA<FairiesApiException>().having(
          (error) => error.code,
          'code',
          'INVALID_RESPONSE',
        ),
      ),
    );
  });

  test('POST /end sends pre-match null fields and parses completed', () async {
    late http.Request captured;
    final client = FairiesApiClient(
      baseUrl: 'http://example.test:8000',
      client: MockClient((request) async {
        captured = request;
        return jsonResponse({'status': 'completed'}, 200);
      }),
    );
    const messages = [ChatMessage(role: 'assistant', content: '挨拶')];

    final response = await client.endSession(
      userId: 'user_end',
      sessionId: 'session_end',
      messages: messages,
    );

    expect(
      captured.url.toString(),
      'http://example.test:8000/sessions/session_end/end',
    );
    expect(jsonDecode(captured.body), {
      'user_id': 'user_end',
      'messages': [
        {'role': 'assistant', 'content': '挨拶'},
      ],
      'analysis': null,
      'match': null,
      'top_candidates': [],
      'after_match_support': null,
    });
    expect(response.status, 'completed');
  });

  test('POST /end sends all persisted match data', () async {
    late Map<String, dynamic> body;
    final client = FairiesApiClient(
      client: MockClient((request) async {
        body = jsonDecode(request.body) as Map<String, dynamic>;
        return jsonResponse({'status': 'completed'}, 200);
      }),
    );
    final matchResponse = MatchResponse.fromJson(_matchJson());

    await client.endSession(
      userId: 'user_end',
      sessionId: 'session_end',
      messages: const [ChatMessage(role: 'user', content: '発言')],
      matchResponse: matchResponse,
    );

    expect(body['analysis'], matchResponse.analysis.toJson());
    expect(body['match'], matchResponse.match.toJson());
    expect(body['top_candidates'], [
      matchResponse.topCandidates.single.toJson(),
    ]);
    expect(body['after_match_support'], isNull);
  });

  test('POST /end sends after-match support when present', () async {
    late Map<String, dynamic> body;
    final json = _matchJson();
    json['after_match_support'] = {
      'first_message_today': '今日の一言',
      'question_in_3days': '3日後の質問',
      'avoid_phrase': '避ける言葉',
      'slow_reply_action': '待つ',
    };
    final client = FairiesApiClient(
      client: MockClient((request) async {
        body = jsonDecode(request.body) as Map<String, dynamic>;
        return jsonResponse({'status': 'completed'}, 200);
      }),
    );

    await client.endSession(
      userId: 'user_end',
      sessionId: 'session_end',
      messages: const [],
      matchResponse: MatchResponse.fromJson(json),
    );

    expect(body['after_match_support'], json['after_match_support']);
  });
}

class ChunkedClient extends http.BaseClient {
  ChunkedClient(this.chunks, {this.statusCode = 200});

  final List<List<int>> chunks;
  final int statusCode;
  http.Request? request;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    this.request = request as http.Request;
    return http.StreamedResponse(
      Stream<List<int>>.fromIterable(chunks),
      statusCode,
      headers: {'content-type': 'application/x-ndjson'},
    );
  }
}

Map<String, dynamic> _matchJson() => {
  'analysis': {
    'personality': '穏やか',
    'values': '誠実',
    'hidden_needs': '安心',
    'communication_style': '丁寧',
    'ideal_partner_type': '対話型',
    'summary': '分析概要',
  },
  'match': {
    'matched_candidate': _candidateJson(),
    'match_score': 85,
    'match_label': '好相性',
    'match_reason': '価値観',
    'possible_concern': '速度差',
    'recommended_first_message': 'こんにちは',
  },
  'top_candidates': [
    {'candidate': _candidateJson(), 'similarity': 0.85},
  ],
  'after_match_support': null,
  'profile_updated': true,
};

Map<String, dynamic> _candidateJson() => {
  'id': 'c01',
  'name': 'あおい',
  'age': 29,
  'personality': '明るい',
  'values': '信頼',
  'hobbies': '読書',
  'communication_style': '率直',
  'relationship_style': '協力的',
  'description': '候補者',
};
