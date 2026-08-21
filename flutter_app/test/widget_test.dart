import 'dart:convert';

import 'package:fairies_app/screens/home_screen.dart';
import 'package:fairies_app/services/fairies_api_client.dart';
import 'package:fairies_app/state/session_state.dart';
import 'package:flutter/material.dart';
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
  testWidgets('displays history and clears input after chat succeeds', (
    WidgetTester tester,
  ) async {
    final state = SessionState(
      apiClient: FairiesApiClient(
        client: MockClient((request) async {
          if (request.url.path == '/sessions') {
            return jsonResponse({
              'user_id': 'user_widget',
              'session_id': 'session_widget',
              'message': {'role': 'assistant', 'content': '画面に表示する挨拶'},
            }, 201);
          }
          return jsonResponse({
            'message': {'role': 'assistant', 'content': '画面に表示する返答'},
          }, 200);
        }),
      ),
    );
    await tester.pumpWidget(MaterialApp(home: HomeScreen(sessionState: state)));

    expect(find.text('フェアリーズ'), findsOneWidget);
    await tester.tap(find.text('セッションを開始'));
    await tester.pumpAndSettle();

    expect(find.text('画面に表示する挨拶'), findsOneWidget);
    expect(state.userId, 'user_widget');
    expect(state.sessionId, 'session_widget');

    await tester.enterText(find.byKey(const Key('chat-input')), '画面からの発言');
    await tester.tap(find.byKey(const Key('send-chat')));
    await tester.pumpAndSettle();

    expect(find.text('画面に表示する挨拶'), findsOneWidget);
    expect(find.text('画面からの発言'), findsOneWidget);
    expect(find.text('画面に表示する返答'), findsOneWidget);
    final input = tester.widget<TextField>(find.byKey(const Key('chat-input')));
    expect(input.controller?.text, isEmpty);
  });

  testWidgets(
    'shows chat error separately and retries without duplicate user text',
    (WidgetTester tester) async {
      var chatAttempts = 0;
      final state = SessionState(
        apiClient: FairiesApiClient(
          client: MockClient((request) async {
            if (request.url.path == '/sessions') {
              return jsonResponse({
                'user_id': 'user_widget_retry',
                'session_id': 'session_widget_retry',
                'message': {'role': 'assistant', 'content': '初回挨拶'},
              }, 201);
            }
            chatAttempts += 1;
            if (chatAttempts == 1) {
              return jsonResponse({
                'error': {
                  'code': 'AI_RESPONSE_FAILED',
                  'message': '通信に失敗しました。',
                },
              }, 502);
            }
            return jsonResponse({
              'message': {'role': 'assistant', 'content': '再試行成功'},
            }, 200);
          }),
        ),
      );
      await tester.pumpWidget(
        MaterialApp(home: HomeScreen(sessionState: state)),
      );
      await tester.tap(find.text('セッションを開始'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byKey(const Key('chat-input')), '一度だけ追加');
      await tester.tap(find.byKey(const Key('send-chat')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('chat-error')), findsOneWidget);
      expect(find.byKey(const Key('message-user')), findsOneWidget);
      expect(find.text('AI_RESPONSE_FAILED'), findsNothing);

      await tester.tap(find.byKey(const Key('retry-chat')));
      await tester.pumpAndSettle();

      expect(find.text('一度だけ追加'), findsOneWidget);
      expect(find.text('再試行成功'), findsOneWidget);
      expect(
        state.messages.where((message) => message.role == 'user'),
        hasLength(1),
      );
    },
  );
}
