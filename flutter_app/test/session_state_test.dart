import 'dart:async';
import 'dart:convert';

import 'package:fairies_app/services/fairies_api_client.dart';
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
}
