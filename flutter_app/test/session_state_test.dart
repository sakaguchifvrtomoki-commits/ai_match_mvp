import 'dart:async';
import 'dart:convert';

import 'package:fairies_app/services/fairies_api_client.dart';
import 'package:fairies_app/models/chat_message.dart';
import 'package:fairies_app/state/session_state.dart';
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
    'successful start stores IDs and exactly one assistant message',
    () async {
      final state = SessionState(
        apiClient: FairiesApiClient(
          client: MockClient(
            (_) async => jsonResponse({
              'user_id': 'user_123',
              'session_id': 'session_456',
              'message': {'role': 'assistant', 'content': '初回メッセージ'},
            }, 201),
          ),
        ),
      );

      await state.startSession();

      expect(state.userId, 'user_123');
      expect(state.sessionId, 'session_456');
      expect(state.messages, hasLength(1));
      expect(state.messages.single.role, 'assistant');
      expect(state.messages.single.content, '初回メッセージ');
      expect(state.errorMessage, isNull);
      expect(state.isLoading, isFalse);
    },
  );

  test('loading is true while the HTTP request is pending', () async {
    final response = Completer<http.Response>();
    final state = SessionState(
      apiClient: FairiesApiClient(client: MockClient((_) => response.future)),
    );

    final start = state.startSession();
    expect(state.isLoading, isTrue);

    response.complete(
      jsonResponse({
        'user_id': 'user_123',
        'session_id': 'session_456',
        'message': {'role': 'assistant', 'content': 'こんにちは'},
      }, 201),
    );
    await start;

    expect(state.isLoading, isFalse);
  });

  test(
    'HTTP failure does not enter messages and a retry can succeed',
    () async {
      var attempt = 0;
      final state = SessionState(
        apiClient: FairiesApiClient(
          client: MockClient((_) async {
            attempt += 1;
            if (attempt == 1) {
              return jsonResponse({
                'error': {
                  'code': 'SESSION_START_FAILED',
                  'message': '再試行してください。',
                },
              }, 500);
            }
            return jsonResponse({
              'user_id': 'user_retry',
              'session_id': 'session_retry',
              'message': {'role': 'assistant', 'content': '成功しました'},
            }, 201);
          }),
        ),
      );

      await state.startSession();
      expect(state.errorCode, 'SESSION_START_FAILED');
      expect(state.errorMessage, '再試行してください。');
      expect(state.messages, isEmpty);

      await state.startSession();
      expect(state.errorMessage, isNull);
      expect(state.userId, 'user_retry');
      expect(state.sessionId, 'session_retry');
      expect(state.messages.single.content, '成功しました');
    },
  );

  test('sendMessage adds user then assistant in order', () async {
    final state = SessionState(
      apiClient: FairiesApiClient(
        client: MockClient((request) async {
          if (request.url.path == '/sessions') {
            return jsonResponse({
              'user_id': 'user_chat',
              'session_id': 'session_chat',
              'message': {'role': 'assistant', 'content': '初回挨拶'},
            }, 201);
          }
          return jsonResponse({
            'message': {'role': 'assistant', 'content': 'Fairyの返答'},
          }, 200);
        }),
      ),
    );
    await state.startSession();

    await state.sendMessage('  ユーザー発言  ');

    expect(state.messages.map((message) => message.role), [
      'assistant',
      'user',
      'assistant',
    ]);
    expect(state.messages[1].content, 'ユーザー発言');
    expect(state.messages[2].content, 'Fairyの返答');
  });

  test('blank text and a missing session do not send', () async {
    var requests = 0;
    final state = SessionState(
      apiClient: FairiesApiClient(
        client: MockClient((_) async {
          requests += 1;
          return jsonResponse({}, 500);
        }),
      ),
    );

    await state.sendMessage('こんにちは');
    await state.sendMessage('   ');

    expect(requests, 0);
    expect(state.messages, isEmpty);
  });

  test(
    'failed chat keeps user message and retry adds only assistant',
    () async {
      var chatAttempts = 0;
      final state = SessionState(
        apiClient: FairiesApiClient(
          client: MockClient((request) async {
            if (request.url.path == '/sessions') {
              return jsonResponse({
                'user_id': 'user_retry_chat',
                'session_id': 'session_retry_chat',
                'message': {'role': 'assistant', 'content': '初回挨拶'},
              }, 201);
            }
            chatAttempts += 1;
            if (chatAttempts == 1) {
              return jsonResponse({
                'error': {
                  'code': 'AI_RESPONSE_FAILED',
                  'message': '再試行してください。',
                },
              }, 502);
            }
            return jsonResponse({
              'message': {'role': 'assistant', 'content': '再試行後の返答'},
            }, 200);
          }),
        ),
      );
      await state.startSession();

      await state.sendMessage('残すユーザー発言');
      expect(state.messages.map((message) => message.role), [
        'assistant',
        'user',
      ]);
      expect(state.messages.last.content, '残すユーザー発言');
      expect(state.errorCode, 'AI_RESPONSE_FAILED');
      expect(state.canRetryLastChat, isTrue);

      await state.sendMessage('残すユーザー発言');
      expect(state.messages, hasLength(2));

      await state.retryLastChat();
      expect(state.messages.map((message) => message.role), [
        'assistant',
        'user',
        'assistant',
      ]);
      expect(state.messages.last.content, '再試行後の返答');
      expect(state.canRetryLastChat, isFalse);
      expect(state.errorMessage, isNull);
    },
  );

  test('a second send is ignored while chat is loading', () async {
    final chatResponse = Completer<http.Response>();
    var chatRequests = 0;
    final state = SessionState(
      apiClient: FairiesApiClient(
        client: MockClient((request) async {
          if (request.url.path == '/sessions') {
            return jsonResponse({
              'user_id': 'user_loading_chat',
              'session_id': 'session_loading_chat',
              'message': {'role': 'assistant', 'content': '初回挨拶'},
            }, 201);
          }
          chatRequests += 1;
          return chatResponse.future;
        }),
      ),
    );
    await state.startSession();

    final firstSend = state.sendMessage('最初の発言');
    await state.sendMessage('二重送信');
    await Future<void>.delayed(Duration.zero);
    expect(state.isLoading, isTrue);
    expect(chatRequests, 1);
    expect(
      state.messages.where((message) => message.role == 'user'),
      hasLength(1),
    );

    chatResponse.complete(
      jsonResponse({
        'message': {'role': 'assistant', 'content': '返答'},
      }, 200),
    );
    await firstSend;
  });

  test('match requires three user messages', () async {
    var requests = 0;
    final state = _matchReadyState(
      MockClient((_) async {
        requests += 1;
        return jsonResponse(_matchJson(), 200);
      }),
      userMessageCount: 2,
    );

    await state.generateMatch();

    expect(requests, 0);
    expect(state.matchResponse, isNull);
  });

  test('match stores response without modifying messages', () async {
    final state = _matchReadyState(
      MockClient(
        (_) async => jsonResponse(_matchJson(profileUpdated: false), 200),
      ),
    );
    final original = List<ChatMessage>.of(state.messages);

    await state.generateMatch();

    expect(state.messages, orderedEquals(original));
    expect(state.matchResponse?.match.matchedCandidate.name, 'あおい');
    expect(state.matchResponse?.profileUpdated, isFalse);
    expect(state.isMatching, isFalse);
  });

  test('matching prevents duplicate requests', () async {
    final pending = Completer<http.Response>();
    var requests = 0;
    final state = _matchReadyState(
      MockClient((_) {
        requests += 1;
        return pending.future;
      }),
    );

    final first = state.generateMatch();
    await state.generateMatch();
    await Future<void>.delayed(Duration.zero);
    expect(state.isMatching, isTrue);
    expect(requests, 1);

    pending.complete(jsonResponse(_matchJson(), 200));
    await first;
    expect(state.isMatching, isFalse);
  });

  test('match API error stays separate from messages', () async {
    final state = _matchReadyState(
      MockClient(
        (_) async => jsonResponse({
          'error': {'code': 'ANALYSIS_FAILED', 'message': '分析できませんでした。'},
        }, 502),
      ),
    );
    final original = List<ChatMessage>.of(state.messages);

    await state.generateMatch();

    expect(state.messages, orderedEquals(original));
    expect(state.errorCode, 'ANALYSIS_FAILED');
    expect(state.matchResponse, isNull);
  });
}

SessionState _matchReadyState(MockClient client, {int userMessageCount = 3}) {
  final state = SessionState(apiClient: FairiesApiClient(client: client));
  state.userId = 'user_match';
  state.sessionId = 'session_match';
  state.messages.add(const ChatMessage(role: 'assistant', content: '挨拶'));
  for (var index = 0; index < userMessageCount; index++) {
    state.messages.add(ChatMessage(role: 'user', content: '発言$index'));
  }
  return state;
}

Map<String, dynamic> _matchJson({bool profileUpdated = true}) => {
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
  'profile_updated': profileUpdated,
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
