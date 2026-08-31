import 'dart:async';
import 'dart:convert';

import 'package:fairies_app/screens/home_screen.dart';
import 'package:fairies_app/models/chat_message.dart';
import 'package:fairies_app/models/match_response.dart';
import 'package:fairies_app/services/fairies_api_client.dart';
import 'package:fairies_app/state/session_state.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

http.Response jsonResponse(Map<String, dynamic> body, int statusCode) {
  return http.Response.bytes(
    utf8.encode(jsonEncode(body)),
    statusCode,
    headers: {'content-type': 'application/json; charset=utf-8'},
  );
}

Future<void> acceptConsentAndStart(WidgetTester tester) async {
  await tester.tap(find.byKey(const Key('consent-accept')));
  await tester.pump();
  await tester.tap(find.byKey(const Key('start-chat')));
  await tester.pumpAndSettle();
}

ScrollableState conversationScrollable(WidgetTester tester) =>
    tester.state<ScrollableState>(
      find
          .descendant(
            of: find.byKey(const Key('conversation-list')),
            matching: find.byType(Scrollable),
          )
          .first,
    );

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets('requires log consent before starting and displays version', (
    WidgetTester tester,
  ) async {
    var sessionRequests = 0;
    Map<String, dynamic>? requestBody;
    final state = SessionState(
      apiClient: FairiesApiClient(
        client: MockClient((request) async {
          sessionRequests += 1;
          requestBody = jsonDecode(request.body) as Map<String, dynamic>;
          return jsonResponse({
            'user_id': 'user_consent',
            'session_id': 'session_consent',
            'message': {'role': 'assistant', 'content': '同意後の挨拶'},
          }, 201);
        }),
      ),
    );

    await tester.pumpWidget(MaterialApp(home: HomeScreen(sessionState: state)));
    await tester.pumpAndSettle();

    expect(find.text('ログ保存への同意確認'), findsOneWidget);
    expect(find.byKey(const Key('fairies-background')), findsOneWidget);
    expect(find.text('v0.2.2'), findsOneWidget);
    expect(find.textContaining('AIとチャットすることで'), findsOneWidget);
    expect(sessionRequests, 0);

    await tester.tap(find.byKey(const Key('start-chat')));
    await tester.pump();
    expect(find.byKey(const Key('consent-validation')), findsOneWidget);
    expect(sessionRequests, 0);

    await acceptConsentAndStart(tester);

    expect(sessionRequests, 1);
    expect(requestBody?['log_consent'], isTrue);
    expect(find.text('同意後の挨拶'), findsOneWidget);
    expect(state.userId, 'user_consent');
    expect(state.sessionId, 'session_consent');
  });

  testWidgets('declining consent blocks use and can return', (
    WidgetTester tester,
  ) async {
    var requests = 0;
    final state = SessionState(
      apiClient: FairiesApiClient(
        client: MockClient((_) async {
          requests += 1;
          return jsonResponse({}, 500);
        }),
      ),
    );
    await tester.pumpWidget(MaterialApp(home: HomeScreen(sessionState: state)));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('consent-decline')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('start-chat')));
    await tester.pump();

    expect(find.byKey(const Key('consent-declined-message')), findsOneWidget);
    expect(find.textContaining('チャットを開始できません'), findsOneWidget);
    expect(requests, 0);

    await tester.tap(find.byKey(const Key('back-to-consent')));
    await tester.pump();
    expect(find.text('ログ保存への同意確認'), findsOneWidget);
    expect(find.byKey(const Key('consent-accept')), findsOneWidget);
  });

  testWidgets('shows session loading until the initial greeting arrives', (
    WidgetTester tester,
  ) async {
    final response = Completer<http.Response>();
    final state = SessionState(
      apiClient: FairiesApiClient(client: MockClient((_) => response.future)),
    );
    await tester.pumpWidget(MaterialApp(home: HomeScreen(sessionState: state)));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('consent-accept')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('start-chat')));
    await tester.pump();

    expect(find.byKey(const Key('session-loading')), findsOneWidget);
    expect(find.text('Fairyを呼んでいます…'), findsOneWidget);
    expect(state.isLoading, isTrue);

    response.complete(
      jsonResponse({
        'user_id': 'user_loading',
        'session_id': 'session_loading',
        'message': {'role': 'assistant', 'content': '到着した初回挨拶'},
      }, 201),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('session-loading')), findsNothing);
    expect(find.text('到着した初回挨拶'), findsOneWidget);
  });

  testWidgets(
    'session error offers retry and succeeds without losing consent',
    (WidgetTester tester) async {
      var attempts = 0;
      final state = SessionState(
        apiClient: FairiesApiClient(
          client: MockClient((_) async {
            attempts += 1;
            if (attempts == 1) {
              return jsonResponse({
                'error': {
                  'code': 'SESSION_START_FAILED',
                  'message': '通信に失敗しました。',
                },
              }, 500);
            }
            return jsonResponse({
              'user_id': 'user_session_retry',
              'session_id': 'session_retry_success',
              'message': {'role': 'assistant', 'content': '再試行後の挨拶'},
            }, 201);
          }),
        ),
      );
      await tester.pumpWidget(
        MaterialApp(home: HomeScreen(sessionState: state)),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('consent-accept')));
      await tester.pump();
      await tester.tap(find.byKey(const Key('start-chat')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('session-loading')), findsNothing);
      expect(find.byKey(const Key('session-error')), findsOneWidget);
      expect(find.text('Fairyを呼べませんでした'), findsOneWidget);
      expect(find.byKey(const Key('session-retry')), findsOneWidget);
      expect(
        tester.widget<OutlinedButton>(find.byKey(const Key('session-retry'))),
        isA<OutlinedButton>(),
      );

      await tester.ensureVisible(find.byKey(const Key('session-retry')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('session-retry')));
      await tester.pumpAndSettle();

      expect(attempts, 2);
      expect(find.byKey(const Key('session-error')), findsNothing);
      expect(find.text('再試行後の挨拶'), findsOneWidget);
    },
  );

  testWidgets('shows chat loading after the user message and clears it', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(320, 568);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final response = Completer<http.Response>();
    final state = SessionState(
      apiClient: FairiesApiClient(client: MockClient((_) => response.future)),
    );
    state.userId = 'user_chat_loading';
    state.sessionId = 'session_chat_loading';
    state.messages.add(const ChatMessage(role: 'assistant', content: '初回挨拶'));
    await tester.pumpWidget(MaterialApp(home: HomeScreen(sessionState: state)));

    await tester.enterText(find.byKey(const Key('chat-input')), 'すぐ表示する発言');
    await tester.tap(find.byKey(const Key('send-chat')));
    await tester.pump();

    expect(
      find.descendant(
        of: find.byKey(const Key('message-user')),
        matching: find.text('すぐ表示する発言'),
      ),
      findsOneWidget,
    );
    expect(find.byKey(const Key('chat-loading')), findsOneWidget);
    expect(find.text('Fairyが考えています…'), findsOneWidget);
    expect(
      tester.widget<IconButton>(find.byKey(const Key('send-chat'))).onPressed,
      isNull,
    );

    response.complete(
      jsonResponse({
        'message': {'role': 'assistant', 'content': 'Fairyの返答'},
      }, 200),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('chat-loading')), findsNothing);
    expect(find.text('Fairyの返答'), findsOneWidget);
  });

  testWidgets('shows the same chat loading while retrying', (
    WidgetTester tester,
  ) async {
    final retryResponse = Completer<http.Response>();
    var attempts = 0;
    final state = SessionState(
      apiClient: FairiesApiClient(
        client: MockClient((_) async {
          attempts += 1;
          if (attempts == 1) {
            return jsonResponse({
              'error': {'code': 'AI_RESPONSE_FAILED', 'message': '失敗'},
            }, 502);
          }
          return retryResponse.future;
        }),
      ),
    );
    state.userId = 'user_retry_loading';
    state.sessionId = 'session_retry_loading';
    await tester.pumpWidget(MaterialApp(home: HomeScreen(sessionState: state)));

    await tester.enterText(find.byKey(const Key('chat-input')), '重複しない発言');
    await tester.tap(find.byKey(const Key('send-chat')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('chat-retry')));
    await tester.pump();

    expect(find.byKey(const Key('chat-loading')), findsOneWidget);
    expect(find.text('Fairyが考えています…'), findsOneWidget);
    expect(
      state.messages.where((message) => message.role == 'user'),
      hasLength(1),
    );

    retryResponse.complete(
      jsonResponse({
        'message': {'role': 'assistant', 'content': '再試行の返答'},
      }, 200),
    );
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('chat-loading')), findsNothing);
  });

  testWidgets('shows match loading and then the existing result', (
    WidgetTester tester,
  ) async {
    final response = Completer<http.Response>();
    final state = SessionState(
      apiClient: FairiesApiClient(client: MockClient((_) => response.future)),
    );
    state.userId = 'user_match_loading';
    state.sessionId = 'session_match_loading';
    state.messages.addAll(const [
      ChatMessage(role: 'user', content: '一件目'),
      ChatMessage(role: 'user', content: '二件目'),
      ChatMessage(role: 'user', content: '三件目'),
    ]);
    await tester.pumpWidget(MaterialApp(home: HomeScreen(sessionState: state)));

    await tester.tap(find.byKey(const Key('generate-match')));
    await tester.pump();

    expect(find.byKey(const Key('match-loading')), findsOneWidget);
    expect(find.text('Fairyがあなたを分析しています…'), findsOneWidget);
    expect(
      tester
          .widget<FilledButton>(find.byKey(const Key('generate-match')))
          .onPressed,
      isNull,
    );

    response.complete(matchStreamResponse(_matchJson()));
    await pumpMatchCompletion(tester, state);

    expect(find.byKey(const Key('match-loading')), findsNothing);
    expect(find.byKey(const Key('match-result')), findsOneWidget);
  });

  testWidgets('match loading follows backend phases without a timer', (
    WidgetTester tester,
  ) async {
    final transport = ControlledStreamClient();
    final state = SessionState(apiClient: FairiesApiClient(client: transport));
    state.userId = 'user_match_phases';
    state.sessionId = 'session_match_phases';
    state.messages.addAll(const [
      ChatMessage(role: 'user', content: '一件目'),
      ChatMessage(role: 'user', content: '二件目'),
      ChatMessage(role: 'user', content: '三件目'),
    ]);
    await tester.pumpWidget(MaterialApp(home: HomeScreen(sessionState: state)));

    await tester.tap(find.byKey(const Key('generate-match')));
    await tester.pump();
    expect(find.text('Fairyがあなたを分析しています…'), findsOneWidget);

    transport.add({'type': 'progress', 'phase': 'analyzing'});
    await tester.pump();
    expect(find.text('Fairyがあなたを分析しています…'), findsOneWidget);

    transport.add({'type': 'progress', 'phase': 'matching'});
    await tester.pump();
    expect(find.text('あなたに合いそうな相手を探しています…'), findsOneWidget);

    transport.add({'type': 'progress', 'phase': 'memorizing'});
    await tester.pump();
    expect(find.text('Fairyが今回の会話を記憶にまとめています…'), findsOneWidget);

    transport.add({'type': 'result', 'data': _matchJson()});
    await transport.closeStream();
    await pumpMatchCompletion(tester, state);
    expect(find.byKey(const Key('match-loading')), findsNothing);
    expect(find.byKey(const Key('match-result')), findsOneWidget);
    expect(state.matchLoadingPhase, isNull);
  });

  testWidgets('match error preserves chat and retry enters result mode', (
    WidgetTester tester,
  ) async {
    var attempts = 0;
    final state = SessionState(
      apiClient: FairiesApiClient(
        client: MockClient((_) async {
          attempts += 1;
          if (attempts == 1) {
            return jsonResponse({
              'error': {'code': 'MATCHING_FAILED', 'message': '処理に失敗しました。'},
            }, 502);
          }
          return matchStreamResponse(_matchJson());
        }),
      ),
    );
    state.userId = 'user_match_retry';
    state.sessionId = 'session_match_retry';
    state.messages.addAll(const [
      ChatMessage(role: 'user', content: '一件目'),
      ChatMessage(role: 'user', content: '二件目'),
      ChatMessage(role: 'user', content: '三件目'),
    ]);
    final original = List<ChatMessage>.of(state.messages);
    await tester.pumpWidget(MaterialApp(home: HomeScreen(sessionState: state)));

    await tester.tap(find.byKey(const Key('generate-match')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('match-loading')), findsNothing);
    expect(find.byKey(const Key('match-error')), findsOneWidget);
    expect(find.text('マッチング結果を取得できませんでした'), findsOneWidget);
    expect(find.byKey(const Key('match-retry')), findsOneWidget);
    expect(
      tester.widget<OutlinedButton>(find.byKey(const Key('match-retry'))),
      isA<OutlinedButton>(),
    );
    expect(find.byKey(const Key('match-result')), findsNothing);
    expect(state.messages, orderedEquals(original));

    await tester.tap(find.byKey(const Key('match-retry')));
    await pumpMatchCompletion(tester, state);

    expect(attempts, 2);
    expect(find.byKey(const Key('match-error')), findsNothing);
    expect(find.byKey(const Key('match-result')), findsOneWidget);
    expect(find.byKey(const Key('chat-input')), findsNothing);
  });

  testWidgets('shows end loading and clears it before the survey', (
    WidgetTester tester,
  ) async {
    final response = Completer<http.Response>();
    final state = SessionState(
      apiClient: FairiesApiClient(client: MockClient((_) => response.future)),
    );
    state.userId = 'user_end_loading';
    state.sessionId = 'session_end_loading';
    await tester.pumpWidget(MaterialApp(home: HomeScreen(sessionState: state)));

    await tester.tap(find.byKey(const Key('end-session')));
    await tester.pump();

    expect(find.byKey(const Key('end-loading')), findsOneWidget);
    expect(find.text('セッションを終了しています…'), findsOneWidget);
    expect(
      tester
          .widget<OutlinedButton>(find.byKey(const Key('end-session')))
          .onPressed,
      isNull,
    );

    response.complete(jsonResponse({'status': 'completed'}, 200));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('end-loading')), findsNothing);
    expect(find.byKey(const Key('session-completed')), findsOneWidget);
  });

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
    await tester.pumpAndSettle();

    expect(find.text('フェアリーズ'), findsOneWidget);
    await acceptConsentAndStart(tester);

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

  testWidgets('chat bubbles use responsive left and right placement', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(320, 568);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final state = SessionState();
    state.userId = 'user_bubbles';
    state.sessionId = 'session_bubbles';
    state.messages.addAll(const [
      ChatMessage(
        role: 'assistant',
        content: 'Fairy側の長いメッセージです。小さな画面でも省略せず自然に折り返して表示します。',
      ),
      ChatMessage(
        role: 'user',
        content: 'user側の長いメッセージです。右側に配置しながら自然に折り返して表示します。',
      ),
    ]);

    await tester.pumpWidget(MaterialApp(home: HomeScreen(sessionState: state)));
    await tester.pumpAndSettle();

    final listRect = tester.getRect(find.byKey(const Key('conversation-list')));
    final fairyRect = tester.getRect(
      find.byKey(const Key('message-assistant')),
    );
    final userRect = tester.getRect(find.byKey(const Key('message-user')));
    expect(fairyRect.center.dx, lessThan(listRect.center.dx));
    expect(userRect.center.dx, greaterThan(listRect.center.dx));
    expect(fairyRect.width, lessThanOrEqualTo(listRect.width * 0.82));
    expect(userRect.width, lessThanOrEqualTo(listRect.width * 0.82));
    expect(find.byKey(const Key('chat-input')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('auto-scrolls when user and assistant messages are added', (
    WidgetTester tester,
  ) async {
    final chatResponse = Completer<http.Response>();
    final state = SessionState(
      apiClient: FairiesApiClient(
        client: MockClient((_) => chatResponse.future),
      ),
    );
    state.userId = 'user_scroll';
    state.sessionId = 'session_scroll';
    for (var index = 0; index < 20; index++) {
      state.messages.add(
        ChatMessage(role: 'assistant', content: 'スクロール用 $index\n複数行です'),
      );
    }
    await tester.pumpWidget(MaterialApp(home: HomeScreen(sessionState: state)));
    await tester.pumpAndSettle();
    final scrollable = conversationScrollable(tester);

    scrollable.position.jumpTo(0);
    await tester.enterText(find.byKey(const Key('chat-input')), '新しいユーザー発言');
    await tester.tap(find.byKey(const Key('send-chat')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 1));
    await tester.pump(const Duration(milliseconds: 250));
    await tester.pump(const Duration(milliseconds: 250));
    expect(state.messages, hasLength(21));
    expect(scrollable.position.maxScrollExtent, greaterThan(0));
    expect(scrollable.position.pixels, greaterThan(0));

    scrollable.position.jumpTo(0);
    chatResponse.complete(
      jsonResponse({
        'message': {'role': 'assistant', 'content': '最新のassistant response'},
      }, 200),
    );
    await tester.pumpAndSettle();
    expect(scrollable.position.pixels, greaterThan(0));
    expect(find.text('最新のassistant response'), findsOneWidget);
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
            if (chatAttempts <= 2) {
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
      await tester.pumpAndSettle();
      await acceptConsentAndStart(tester);
      tester.view.physicalSize = const Size(320, 568);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpAndSettle();
      for (var index = 0; index < 15; index++) {
        state.messages.add(
          ChatMessage(role: 'assistant', content: 'retry用履歴 $index\n複数行です'),
        );
      }
      state.notifyListeners();
      await tester.pumpAndSettle();
      await tester.enterText(find.byKey(const Key('chat-input')), '一度だけ追加');
      await tester.tap(find.byKey(const Key('send-chat')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('chat-error')), findsOneWidget);
      expect(find.text('Fairyから返答を受け取れませんでした'), findsOneWidget);
      expect(find.byKey(const Key('chat-retry')), findsOneWidget);
      expect(find.text('もう一度試す'), findsOneWidget);
      expect(find.text('再試行'), findsNothing);
      final retryButton = tester.widget<OutlinedButton>(
        find.byKey(const Key('chat-retry')),
      );
      expect(
        retryButton.style?.minimumSize?.resolve(<WidgetState>{})?.height,
        greaterThanOrEqualTo(44),
      );
      expect(find.byKey(const Key('message-user')), findsOneWidget);
      expect(find.text('AI_RESPONSE_FAILED'), findsNothing);

      final scrollable = conversationScrollable(tester);
      scrollable.position.jumpTo(0);
      await tester.tap(find.byKey(const Key('chat-retry')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('chat-loading')), findsNothing);
      expect(find.byKey(const Key('chat-error')), findsOneWidget);
      expect(find.byKey(const Key('chat-retry')), findsOneWidget);
      expect(
        state.messages.where((message) => message.role == 'user'),
        hasLength(1),
      );

      await tester.tap(find.byKey(const Key('chat-retry')));
      await tester.pumpAndSettle();

      expect(find.text('一度だけ追加'), findsOneWidget);
      expect(find.text('再試行成功'), findsOneWidget);
      expect(
        state.messages.where((message) => message.role == 'user'),
        hasLength(1),
      );
      expect(scrollable.position.pixels, greaterThan(0));
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('displays primary match results without changing history', (
    WidgetTester tester,
  ) async {
    final state = SessionState(
      apiClient: FairiesApiClient(
        client: MockClient((_) async => matchStreamResponse(_matchJson())),
      ),
    );
    state.userId = 'user_widget_match';
    state.sessionId = 'session_widget_match';
    state.messages.addAll(const [
      ChatMessage(role: 'assistant', content: '初回挨拶'),
      ChatMessage(role: 'user', content: '一件目'),
      ChatMessage(role: 'user', content: '二件目'),
      ChatMessage(role: 'user', content: '三件目'),
    ]);
    final messageCount = state.messages.length;
    await tester.pumpWidget(MaterialApp(home: HomeScreen(sessionState: state)));

    await tester.tap(find.byKey(const Key('generate-match')));
    await pumpMatchCompletion(tester, state);

    expect(find.byKey(const Key('match-result')), findsOneWidget);
    for (final key in const [
      Key('analysis-result-section'),
      Key('matching-result-section'),
      Key('warning-result-section'),
      Key('message-result-section'),
      Key('other-candidates-result-section'),
      Key('support-result-section'),
      Key('fairy-profile-summary-section'),
      Key('profile-update-result-section'),
    ]) {
      expect(find.byKey(key), findsOneWidget);
    }
    for (final label in const [
      '性格傾向',
      '価値観',
      '隠れた欲求',
      '会話スタイル',
      '理想の相手像',
      '一言要約',
    ]) {
      expect(find.text(label), findsOneWidget);
    }
    expect(find.text('穏やか'), findsOneWidget);
    expect(find.text('誠実'), findsOneWidget);
    expect(find.text('安心'), findsOneWidget);
    expect(find.text('丁寧'), findsOneWidget);
    expect(find.text('対話型'), findsOneWidget);
    expect(find.text('分析概要'), findsOneWidget);
    expect(find.text('1位候補'), findsOneWidget);
    expect(find.text('1位候補の説明'), findsOneWidget);
    expect(find.textContaining('85点'), findsOneWidget);
    expect(find.text('価値観が近い'), findsOneWidget);
    expect(find.text('注意点'), findsOneWidget);
    expect(find.text('速度差'), findsOneWidget);
    expect(find.text('おすすめの最初のメッセージ'), findsOneWidget);
    expect(find.text('こんにちは'), findsOneWidget);
    expect(find.text('2位'), findsOneWidget);
    expect(find.text('みどり（31歳）'), findsOneWidget);
    expect(find.text('落ち着いて話せる候補者'), findsOneWidget);
    expect(find.text('3位'), findsOneWidget);
    expect(find.text('ひかり（27歳）'), findsOneWidget);
    expect(find.text('活動的な候補者'), findsOneWidget);
    expect(find.text('マッチ後支援'), findsOneWidget);
    expect(find.text('今日送る一言'), findsOneWidget);
    expect(find.text('3日以内に聞く質問'), findsOneWidget);
    expect(find.text('避けたほうがいい一言'), findsOneWidget);
    expect(find.text('返信が遅いときの対応'), findsOneWidget);
    expect(
      find.byKey(const Key('fairy-profile-summary-section')),
      findsOneWidget,
    );
    expect(find.text('Fairyが覚えたプロフィール'), findsOneWidget);
    expect(find.text('Fairyの理解'), findsOneWidget);
    expect(find.text('長期的な理解'), findsOneWidget);
    expect(find.text('・信頼'), findsOneWidget);
    expect(find.text('・対話'), findsOneWidget);
    expect(find.text('関係スタイル'), findsOneWidget);
    expect(find.text('じっくり関係を築く'), findsOneWidget);
    expect(find.text('合いそうな相手'), findsOneWidget);
    expect(find.text('誠実な相手'), findsOneWidget);
    expect(find.textContaining('profile_updated'), findsNothing);
    expect(find.text('false'), findsNothing);
    expect(find.text('マッチング結果を表示しています。プロフィールは更新されませんでした。'), findsOneWidget);
    expect(state.messages, hasLength(messageCount));

    final listRect = tester.getRect(find.byKey(const Key('conversation-list')));
    final resultRect = tester.getRect(find.byKey(const Key('match-result')));
    final scrollable = conversationScrollable(tester);
    expect(resultRect.top, greaterThanOrEqualTo(listRect.top - 1));
    expect(resultRect.top, lessThan(listRect.bottom));
    expect(
      scrollable.position.pixels,
      lessThan(scrollable.position.maxScrollExtent),
    );

    final positionAfterMatch = scrollable.position.pixels;
    state.notifyListeners();
    await tester.pumpAndSettle();
    expect(scrollable.position.pixels, positionAfterMatch);
  });

  testWidgets(
    'result mode resumes the same session and requires a new user message',
    (WidgetTester tester) async {
      var matchRequests = 0;
      var chatRequests = 0;
      final state = SessionState(
        apiClient: FairiesApiClient(
          client: MockClient((request) async {
            if (request.url.path == '/match/stream') {
              matchRequests += 1;
              return matchStreamResponse(_matchJson());
            }
            if (request.url.path.endsWith('/end')) {
              return jsonResponse({'status': 'completed'}, 200);
            }
            chatRequests += 1;
            return jsonResponse({
              'message': {'role': 'assistant', 'content': '続きへの返答'},
            }, 200);
          }),
        ),
      );
      state.userId = 'user_result_mode';
      state.sessionId = 'session_result_mode';
      state.messages.addAll(const [
        ChatMessage(role: 'assistant', content: '初回挨拶'),
        ChatMessage(role: 'user', content: '一件目'),
        ChatMessage(role: 'user', content: '二件目'),
        ChatMessage(role: 'user', content: '三件目'),
      ]);
      final originalMessages = List<ChatMessage>.of(state.messages);

      await tester.pumpWidget(
        MaterialApp(home: HomeScreen(sessionState: state)),
      );
      expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('generate-match')))
            .onPressed,
        isNotNull,
      );

      await tester.tap(find.byKey(const Key('generate-match')));
      await pumpMatchCompletion(tester, state);

      expect(matchRequests, 1);
      expect(find.byKey(const Key('match-result')), findsOneWidget);
      expect(find.byKey(const Key('chat-input')), findsNothing);
      expect(find.byKey(const Key('send-chat')), findsNothing);
      expect(find.byKey(const Key('generate-match')), findsNothing);
      expect(find.byKey(const Key('resume-conversation')), findsOneWidget);
      expect(find.text('もう一度会話する'), findsOneWidget);
      expect(find.byKey(const Key('end-session')), findsOneWidget);
      expect(find.text('終わる'), findsOneWidget);

      await tester.tap(find.byKey(const Key('resume-conversation')));
      await tester.pumpAndSettle();

      expect(state.userId, 'user_result_mode');
      expect(state.sessionId, 'session_result_mode');
      expect(state.messages, orderedEquals(originalMessages));
      expect(state.matchResponse, isNull);
      expect(find.byKey(const Key('match-result')), findsNothing);
      expect(find.byKey(const Key('chat-input')), findsOneWidget);
      expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('generate-match')))
            .onPressed,
        isNull,
      );

      await tester.enterText(find.byKey(const Key('chat-input')), '新しい四件目');
      await tester.tap(find.byKey(const Key('send-chat')));
      await tester.pumpAndSettle();

      expect(chatRequests, 1);
      expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('generate-match')))
            .onPressed,
        isNotNull,
      );
      await tester.tap(find.byKey(const Key('generate-match')));
      await pumpMatchCompletion(tester, state);

      expect(matchRequests, 2);
      expect(find.byKey(const Key('match-result')), findsOneWidget);
      expect(find.byKey(const Key('chat-input')), findsNothing);
      expect(find.byKey(const Key('generate-match')), findsNothing);

      await tester.tap(find.byKey(const Key('end-session')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('session-completed')), findsOneWidget);
    },
  );

  testWidgets('hides null and empty analysis fields', (
    WidgetTester tester,
  ) async {
    final json = _matchJson();
    json['profile_updated'] = true;
    json['fairy_profile_summary'] = {
      'understanding': '',
      'values': <String>[],
      'relationship_style': '',
      'good_match': '',
    };
    final analysis = Map<String, dynamic>.from(
      json['analysis'] as Map<String, dynamic>,
    );
    json['analysis'] = analysis;
    analysis['personality'] = null;
    analysis['values'] = '';
    final state = SessionState();
    state.userId = 'user_partial_analysis';
    state.sessionId = 'session_partial_analysis';
    state.messages.add(const ChatMessage(role: 'assistant', content: '挨拶'));
    state.matchResponse = MatchResponse.fromJson(json);

    await tester.pumpWidget(MaterialApp(home: HomeScreen(sessionState: state)));

    expect(find.textContaining('null'), findsNothing);
    expect(find.text('性格傾向'), findsNothing);
    expect(find.text('価値観'), findsNothing);
    expect(find.text('隠れた欲求'), findsOneWidget);
    expect(find.text('安心'), findsOneWidget);
    expect(find.text('Fairyのプロフィールを更新しました'), findsOneWidget);
    expect(find.text('Fairyが覚えたプロフィール'), findsNothing);
  });

  testWidgets(
    'fairy profile summary remains reachable before update status on a small screen',
    (WidgetTester tester) async {
      tester.view.physicalSize = const Size(320, 568);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final json = _matchJson();
      json['profile_updated'] = true;
      json['fairy_profile_summary'] = {
        'understanding': '実プロフィールから生成されたFairyの理解',
        'values': ['世界観', '対話', '段階的な改善', '生成AI', '体験'],
        'relationship_style': '',
        'good_match': '丁寧に受け止めてくれる相手',
      };
      final state = SessionState();
      state.userId = 'user_profile_scroll';
      state.sessionId = 'session_profile_scroll';
      state.messages.addAll(const [
        ChatMessage(role: 'assistant', content: '初回挨拶'),
        ChatMessage(role: 'user', content: '一件目'),
        ChatMessage(role: 'user', content: '二件目'),
        ChatMessage(role: 'user', content: '三件目'),
      ]);
      state.matchResponse = MatchResponse.fromJson(json);

      await tester.pumpWidget(
        MaterialApp(home: HomeScreen(sessionState: state)),
      );
      await tester.pumpAndSettle();

      final profileSection = find.byKey(
        const Key('fairy-profile-summary-section'),
      );
      final updateStatus = find.text('Fairyのプロフィールを更新しました');
      final scrollableFinder = find
          .descendant(
            of: find.byKey(const Key('conversation-list')),
            matching: find.byType(Scrollable),
          )
          .first;

      expect(profileSection, findsOneWidget);
      expect(find.text('Fairyが覚えたプロフィール'), findsOneWidget);
      expect(find.text('実プロフィールから生成されたFairyの理解'), findsOneWidget);
      expect(find.text('・世界観'), findsOneWidget);
      expect(find.text('・体験'), findsOneWidget);
      expect(find.text('丁寧に受け止めてくれる相手'), findsOneWidget);
      expect(find.text('関係スタイル'), findsNothing);
      expect(updateStatus, findsOneWidget);
      expect(
        tester.getTopLeft(find.text('マッチ後支援')).dy,
        lessThan(tester.getTopLeft(profileSection).dy),
      );
      expect(
        tester.getTopLeft(profileSection).dy,
        lessThan(tester.getTopLeft(updateStatus).dy),
      );

      await tester.scrollUntilVisible(
        profileSection,
        300,
        scrollable: scrollableFinder,
      );
      await tester.pumpAndSettle();

      final viewport = tester.getRect(
        find.byKey(const Key('conversation-list')),
      );
      final sectionRect = tester.getRect(profileSection);
      expect(sectionRect.bottom, greaterThan(viewport.top));
      expect(sectionRect.top, lessThan(viewport.bottom));

      await tester.scrollUntilVisible(
        updateStatus,
        200,
        scrollable: scrollableFinder,
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('long match result fits a small screen without overflow', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(320, 568);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final json = _matchJson();
    final match = Map<String, dynamic>.from(
      json['match'] as Map<String, dynamic>,
    );
    json['match'] = match;
    final longText = List.filled(20, '互いの価値観を尊重しながら、落ち着いて対話を重ねられる関係です。').join();
    match['match_reason'] = longText;
    match['possible_concern'] = longText;
    match['recommended_first_message'] = longText;

    final state = SessionState();
    state.userId = 'user_small_screen';
    state.sessionId = 'session_small_screen';
    state.matchResponse = MatchResponse.fromJson(json);

    await tester.pumpWidget(MaterialApp(home: HomeScreen(sessionState: state)));
    await tester.pumpAndSettle();

    expect(find.text(longText), findsNWidgets(3));
    expect(find.byKey(const Key('match-result')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('successful end opens survey and launches the legacy URL', (
    WidgetTester tester,
  ) async {
    Uri? launchedUri;
    final state = SessionState(
      apiClient: FairiesApiClient(
        client: MockClient(
          (_) async => jsonResponse({'status': 'completed'}, 200),
        ),
      ),
    );
    state.userId = 'user_widget_end';
    state.sessionId = 'session_widget_end';
    state.messages.addAll(const [
      ChatMessage(role: 'assistant', content: '終了後も残る挨拶'),
      ChatMessage(role: 'user', content: '終了後も残る発言'),
    ]);
    await tester.pumpWidget(
      MaterialApp(
        home: HomeScreen(
          sessionState: state,
          surveyLauncher: (uri) async {
            launchedUri = uri;
            return true;
          },
        ),
      ),
    );

    await tester.tap(find.byKey(const Key('end-session')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('session-completed')), findsOneWidget);
    expect(find.text('ご利用ありがとうございました'), findsOneWidget);
    expect(find.byKey(const Key('open-survey')), findsOneWidget);
    expect(find.byKey(const Key('skip-survey')), findsOneWidget);
    expect(state.isSessionCompleted, isTrue);

    await tester.tap(find.byKey(const Key('open-survey')));
    await tester.pumpAndSettle();

    expect(
      launchedUri.toString(),
      'https://docs.google.com/forms/d/e/1FAIpQLSeEl3FGWUk_-B7CtGLBOq1YNeeRNcClNibd-8ikF_Weh6rE9A/viewform',
    );
    expect(find.byKey(const Key('new-session')), findsOneWidget);
  });

  testWidgets('failed end keeps result mode and retry opens survey', (
    WidgetTester tester,
  ) async {
    var attempts = 0;
    final state = SessionState(
      apiClient: FairiesApiClient(
        client: MockClient((_) async {
          attempts += 1;
          if (attempts == 1) {
            return jsonResponse({
              'error': {'code': 'SESSION_END_FAILED', 'message': '終了できませんでした。'},
            }, 500);
          }
          return jsonResponse({'status': 'completed'}, 200);
        }),
      ),
    );
    state.userId = 'user_failed_end';
    state.sessionId = 'session_failed_end';
    state.messages.add(
      const ChatMessage(role: 'assistant', content: '維持される会話'),
    );
    state.matchResponse = MatchResponse.fromJson(_matchJson());
    await tester.pumpWidget(MaterialApp(home: HomeScreen(sessionState: state)));

    await tester.tap(find.byKey(const Key('end-session')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('session-completed')), findsNothing);
    expect(find.byKey(const Key('end-loading')), findsNothing);
    expect(find.byKey(const Key('match-result')), findsOneWidget);
    expect(find.byKey(const Key('end-error')), findsOneWidget);
    expect(find.text('セッションを終了できませんでした'), findsOneWidget);
    expect(find.byKey(const Key('end-retry')), findsOneWidget);
    expect(
      tester.widget<OutlinedButton>(find.byKey(const Key('end-retry'))),
      isA<OutlinedButton>(),
    );
    expect(state.messages.single.content, '維持される会話');
    expect(find.text('終了できませんでした。'), findsOneWidget);
    expect(state.isSessionCompleted, isFalse);

    await tester.tap(find.byKey(const Key('end-retry')));
    await tester.pumpAndSettle();

    expect(attempts, 2);
    expect(find.byKey(const Key('end-error')), findsNothing);
    expect(find.byKey(const Key('session-completed')), findsOneWidget);
  });

  testWidgets('skip then new session resets temporary UI and preserves user', (
    WidgetTester tester,
  ) async {
    var sessionRequests = 0;
    final state = SessionState(
      apiClient: FairiesApiClient(
        client: MockClient((request) async {
          if (request.url.path.endsWith('/end')) {
            return jsonResponse({'status': 'completed'}, 200);
          }
          if (request.url.path == '/sessions') {
            sessionRequests += 1;
            return jsonResponse({
              'user_id': 'user_same',
              'session_id': 'session_new',
              'message': {'role': 'assistant', 'content': '新しい初回挨拶'},
            }, 201);
          }
          return jsonResponse({}, 500);
        }),
      ),
    );
    state.userId = 'user_same';
    state.sessionId = 'session_old';
    state.messages.addAll(const [
      ChatMessage(role: 'assistant', content: '前回の挨拶'),
      ChatMessage(role: 'user', content: '前回の発言'),
    ]);
    state.matchResponse = MatchResponse.fromJson(_matchJson());
    await tester.pumpWidget(MaterialApp(home: HomeScreen(sessionState: state)));

    await tester.tap(find.byKey(const Key('end-session')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('skip-survey')));
    await tester.pump();
    expect(find.byKey(const Key('new-session')), findsOneWidget);

    await tester.tap(find.byKey(const Key('new-session')));
    await tester.pump();

    expect(sessionRequests, 0);
    expect(state.userId, 'user_same');
    expect(state.sessionId, isNull);
    expect(state.messages, isEmpty);
    expect(state.matchResponse, isNull);
    expect(state.isSessionCompleted, isFalse);
    expect(find.text('ログ保存への同意確認'), findsOneWidget);

    await acceptConsentAndStart(tester);

    expect(sessionRequests, 1);
    expect(state.userId, 'user_same');
    expect(state.sessionId, 'session_new');
    expect(state.messages, hasLength(1));
    expect(state.messages.single.content, '新しい初回挨拶');
    expect(find.text('前回の挨拶'), findsNothing);
    expect(find.text('前回の発言'), findsNothing);
    final input = tester.widget<TextField>(find.byKey(const Key('chat-input')));
    expect(input.controller?.text, isEmpty);
    expect(conversationScrollable(tester).position.pixels, 0);
  });
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
    'matched_candidate': {
      'id': 'c01',
      'name': 'あおい',
      'age': 29,
      'personality': '明るい',
      'values': '信頼',
      'hobbies': '読書',
      'communication_style': '率直',
      'relationship_style': '協力的',
      'description': '1位候補の説明',
    },
    'match_score': 85,
    'match_label': '好相性',
    'match_reason': '価値観が近い',
    'possible_concern': '速度差',
    'recommended_first_message': 'こんにちは',
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
        'description': '1位候補の説明',
      },
      'similarity': 0.85,
    },
    {
      'candidate': {
        'id': 'c02',
        'name': 'みどり',
        'age': 31,
        'personality': '穏やか',
        'values': '調和',
        'hobbies': '散歩',
        'communication_style': '丁寧',
        'relationship_style': '安定',
        'description': '落ち着いて話せる候補者',
      },
      'similarity': 0.8,
    },
    {
      'candidate': {
        'id': 'c03',
        'name': 'ひかり',
        'age': 27,
        'personality': '活発',
        'values': '挑戦',
        'hobbies': '旅行',
        'communication_style': '快活',
        'relationship_style': '行動的',
        'description': '活動的な候補者',
      },
      'similarity': 0.75,
    },
  ],
  'after_match_support': {
    'first_message_today': '挨拶',
    'question_in_3days': '最近どう？',
    'avoid_phrase': '決めつけ',
    'slow_reply_action': '待つ',
  },
  'fairy_profile_summary': {
    'understanding': '長期的な理解',
    'values': ['信頼', '対話'],
    'relationship_style': 'じっくり関係を築く',
    'good_match': '誠実な相手',
  },
  'profile_updated': false,
};

http.Response matchStreamResponse(Map<String, dynamic> result) =>
    http.Response.bytes(
      utf8.encode(
        [
          jsonEncode({'type': 'progress', 'phase': 'analyzing'}),
          jsonEncode({'type': 'progress', 'phase': 'matching'}),
          jsonEncode({'type': 'progress', 'phase': 'memorizing'}),
          jsonEncode({'type': 'result', 'data': result}),
          '',
        ].join('\n'),
      ),
      200,
      headers: {'content-type': 'application/x-ndjson'},
    );

Future<void> pumpMatchCompletion(
  WidgetTester tester,
  SessionState state,
) async {
  for (var attempt = 0; attempt < 20 && state.isMatching; attempt++) {
    await tester.runAsync(Future<void>.value);
    await tester.pump();
  }
  await tester.pump(const Duration(milliseconds: 300));
  await tester.pump(const Duration(milliseconds: 300));
}

class ControlledStreamClient extends http.BaseClient {
  final StreamController<List<int>> _controller = StreamController<List<int>>();

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    return http.StreamedResponse(
      _controller.stream,
      200,
      headers: {'content-type': 'application/x-ndjson'},
    );
  }

  void add(Map<String, dynamic> event) {
    _controller.add(utf8.encode('${jsonEncode(event)}\n'));
  }

  Future<void> closeStream() => _controller.close();
}
