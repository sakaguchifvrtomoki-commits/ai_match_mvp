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
  testWidgets('starts a session and displays the initial Fairy message', (
    WidgetTester tester,
  ) async {
    final state = SessionState(
      apiClient: FairiesApiClient(
        client: MockClient(
          (_) async => jsonResponse({
            'user_id': 'user_widget',
            'session_id': 'session_widget',
            'message': {'role': 'assistant', 'content': '画面に表示する挨拶'},
          }, 201),
        ),
      ),
    );
    await tester.pumpWidget(MaterialApp(home: HomeScreen(sessionState: state)));

    expect(find.text('フェアリーズ'), findsOneWidget);
    await tester.tap(find.text('セッションを開始'));
    await tester.pumpAndSettle();

    expect(find.text('画面に表示する挨拶'), findsOneWidget);
    expect(state.userId, 'user_widget');
    expect(state.sessionId, 'session_widget');
  });
}
