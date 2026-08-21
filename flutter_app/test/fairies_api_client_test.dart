import 'dart:convert';

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
}
