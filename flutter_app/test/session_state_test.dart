import 'dart:async';
import 'dart:convert';

import 'package:fairies_app/services/fairies_api_client.dart';
import 'package:fairies_app/services/user_storage.dart';
import 'package:fairies_app/models/chat_message.dart';
import 'package:fairies_app/models/match_response.dart';
import 'package:fairies_app/models/match_loading_phase.dart';
import 'package:fairies_app/state/session_state.dart';
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

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

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

      await waitForUserIdLoad(state);
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

    await waitForUserIdLoad(state);
    final start = state.startSession();
    await Future<void>.delayed(Duration.zero);
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

      await waitForUserIdLoad(state);
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
    await waitForUserIdLoad(state);
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
      await waitForUserIdLoad(state);
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
    await waitForUserIdLoad(state);
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
        return matchStreamResponse(_matchJson());
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
        (_) async => matchStreamResponse(_matchJson(profileUpdated: false)),
      ),
    );
    final original = List<ChatMessage>.of(state.messages);

    await state.generateMatch();

    expect(state.messages, orderedEquals(original));
    expect(state.matchResponse?.match.matchedCandidate.name, 'あおい');
    expect(state.matchResponse?.profileUpdated, isFalse);
    expect(state.isMatching, isFalse);
  });

  test(
    'result mode blocks chat and rematch until a new user message',
    () async {
      var matchRequests = 0;
      var chatRequests = 0;
      final state = _matchReadyState(
        MockClient((request) async {
          if (request.url.path == '/match/stream') {
            matchRequests += 1;
            return matchStreamResponse(_matchJson());
          }
          chatRequests += 1;
          return jsonResponse({
            'message': {'role': 'assistant', 'content': '続きの返答'},
          }, 200);
        }),
      );
      final originalUserId = state.userId;
      final originalSessionId = state.sessionId;
      final originalMessages = List<ChatMessage>.of(state.messages);

      await state.generateMatch();
      await state.sendMessage('結果表示中には送れない');
      await state.generateMatch();

      expect(matchRequests, 1);
      expect(chatRequests, 0);
      expect(state.messages, orderedEquals(originalMessages));

      expect(state.resumeConversationAfterMatch(), isTrue);
      expect(state.userId, originalUserId);
      expect(state.sessionId, originalSessionId);
      expect(state.messages, orderedEquals(originalMessages));
      expect(state.matchResponse, isNull);
      expect(state.canMatch, isFalse);

      await state.sendMessage('新しい発言');

      expect(chatRequests, 1);
      expect(state.canMatch, isTrue);
      await state.generateMatch();
      expect(matchRequests, 2);
      expect(state.matchResponse, isNotNull);
      expect(state.canMatch, isFalse);
    },
  );

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

    pending.complete(matchStreamResponse(_matchJson()));
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

  test(
    'terminal stream error clears loading and preserves retry state',
    () async {
      var attempts = 0;
      final state = _matchReadyState(
        MockClient((_) async {
          attempts += 1;
          if (attempts == 1) {
            return ndjsonResponse([
              {'type': 'progress', 'phase': 'analyzing'},
              {
                'type': 'error',
                'error': {'code': 'ANALYSIS_FAILED', 'message': '分析できませんでした。'},
              },
            ]);
          }
          return matchStreamResponse(_matchJson());
        }),
      );
      final original = List<ChatMessage>.of(state.messages);

      await state.generateMatch();

      expect(state.isMatching, isFalse);
      expect(state.matchLoadingPhase, isNull);
      expect(state.errorCode, 'ANALYSIS_FAILED');
      expect(state.messages, orderedEquals(original));

      final retry = state.generateMatch();
      expect(state.isMatching, isTrue);
      expect(state.matchLoadingPhase, MatchLoadingPhase.analyzing);
      await retry;
      expect(state.matchResponse, isNotNull);
      expect(state.matchLoadingPhase, isNull);
    },
  );

  test(
    'malformed and transport failures never leave the match spinner active',
    () async {
      final malformed = _matchReadyState(
        MockClient((_) async => http.Response('{bad-json}\n', 200)),
      );
      await malformed.generateMatch();
      expect(malformed.errorCode, 'INVALID_RESPONSE');
      expect(malformed.isMatching, isFalse);
      expect(malformed.matchLoadingPhase, isNull);

      final disconnected = _matchReadyState(
        MockClient((_) async => throw Exception('connection closed')),
      );
      await disconnected.generateMatch();
      expect(disconnected.errorCode, 'NETWORK_ERROR');
      expect(disconnected.isMatching, isFalse);
      expect(disconnected.matchLoadingPhase, isNull);
    },
  );

  test('end marks session completed and preserves state', () async {
    final state = _endReadyState(
      MockClient((_) async => jsonResponse({'status': 'completed'}, 200)),
    );
    final originalMessages = List<ChatMessage>.of(state.messages);
    final originalMatch = state.matchResponse;

    await state.endSession();

    expect(state.isSessionCompleted, isTrue);
    expect(state.isEnding, isFalse);
    expect(state.userId, 'user_end');
    expect(state.sessionId, 'session_end');
    expect(state.messages, orderedEquals(originalMessages));
    expect(state.matchResponse, same(originalMatch));
  });

  test('new session preparation clears temporary state but preserves user', () {
    final state = _endReadyState(
      MockClient((_) async => jsonResponse({'status': 'completed'}, 200)),
    );
    state.isSessionCompleted = true;
    state.errorCode = 'OLD_ERROR';
    state.errorMessage = '前回のエラー';

    final prepared = state.prepareForNewSession();

    expect(prepared, isTrue);
    expect(state.userId, 'user_end');
    expect(state.sessionId, isNull);
    expect(state.messages, isEmpty);
    expect(state.matchResponse, isNull);
    expect(state.isSessionCompleted, isFalse);
    expect(state.canRetryLastChat, isFalse);
    expect(state.errorCode, isNull);
    expect(state.errorMessage, isNull);
    expect(state.isLoading, isFalse);
    expect(state.isMatching, isFalse);
    expect(state.isEnding, isFalse);
  });

  test('failed end preserves state and can retry', () async {
    var attempts = 0;
    final state = _endReadyState(
      MockClient((_) async {
        attempts += 1;
        if (attempts == 1) {
          return jsonResponse({
            'error': {'code': 'SESSION_END_FAILED', 'message': '終了処理に失敗しました。'},
          }, 500);
        }
        return jsonResponse({'status': 'completed'}, 200);
      }),
    );
    final originalMessages = List<ChatMessage>.of(state.messages);
    final originalMatch = state.matchResponse;

    await state.endSession();
    expect(state.isSessionCompleted, isFalse);
    expect(state.errorCode, 'SESSION_END_FAILED');
    expect(state.messages, orderedEquals(originalMessages));
    expect(state.matchResponse, same(originalMatch));

    await state.endSession();
    expect(state.isSessionCompleted, isTrue);
    expect(attempts, 2);
  });

  test('ending prevents duplicate requests', () async {
    final pending = Completer<http.Response>();
    var requests = 0;
    final state = _endReadyState(
      MockClient((_) {
        requests += 1;
        return pending.future;
      }),
    );

    final first = state.endSession();
    await state.endSession();
    await Future<void>.delayed(Duration.zero);
    expect(state.isEnding, isTrue);
    expect(requests, 1);

    pending.complete(jsonResponse({'status': 'completed'}, 200));
    await first;
    expect(state.isSessionCompleted, isTrue);
  });

  test('loads a stored user ID and sends it to the next session', () async {
    late Map<String, dynamic> requestBody;
    final storage = FakeUserStorage(value: 'user_persisted');
    final state = SessionState(
      userStorage: storage,
      apiClient: FairiesApiClient(
        client: MockClient((request) async {
          requestBody = jsonDecode(request.body) as Map<String, dynamic>;
          return jsonResponse({
            'user_id': 'user_persisted',
            'session_id': 'session_new',
            'message': {'role': 'assistant', 'content': '新しい挨拶'},
          }, 201);
        }),
      ),
    );

    await waitForUserIdLoad(state);
    await state.startSession();

    expect(state.isUserStorageReady, isTrue);
    expect(requestBody['user_id'], 'user_persisted');
    expect(state.sessionId, 'session_new');
    expect(storage.savedValues, ['user_persisted']);
  });

  test('missing stored ID sends null and saves the response ID', () async {
    late Map<String, dynamic> requestBody;
    final storage = FakeUserStorage();
    final state = SessionState(
      userStorage: storage,
      apiClient: FairiesApiClient(
        client: MockClient((request) async {
          requestBody = jsonDecode(request.body) as Map<String, dynamic>;
          return jsonResponse({
            'user_id': 'user_created',
            'session_id': 'session_created',
            'message': {'role': 'assistant', 'content': '挨拶'},
          }, 201);
        }),
      ),
    );

    await waitForUserIdLoad(state);
    await state.startSession();

    expect(requestBody['user_id'], isNull);
    expect(storage.savedValues, ['user_created']);
  });

  test('a failed initial user ID load blocks session requests', () async {
    var requests = 0;
    final state = SessionState(
      userStorage: FakeUserStorage(
        loadAttempts: [() => Future<String?>.error(Exception('load failed'))],
      ),
      apiClient: FairiesApiClient(
        client: MockClient((_) async {
          requests += 1;
          return jsonResponse({}, 500);
        }),
      ),
    );
    await Future<void>.delayed(Duration.zero);

    expect(state.userIdLoadState, UserIdLoadState.failed);
    await state.startSession();

    expect(requests, 0);
    expect(state.storageErrorCode, 'USER_ID_LOAD_FAILED');
  });

  test('a failed load and a successful empty load are distinct states', () async {
    final failed = SessionState(
      userStorage: FakeUserStorage(
        loadAttempts: [() => Future<String?>.error(Exception('load failed'))],
      ),
    );
    final empty = SessionState(userStorage: FakeUserStorage());
    await Future<void>.delayed(Duration.zero);

    expect(failed.userIdLoadState, UserIdLoadState.failed);
    expect(failed.isUserStorageReady, isFalse);
    expect(empty.userIdLoadState, UserIdLoadState.loaded);
    expect(empty.isUserStorageReady, isTrue);
    expect(empty.userId, isNull);
    expect(empty.storageErrorMessage, isNull);
  });

  test('retry succeeds with a stored user ID', () async {
    final storage = FakeUserStorage(
      loadAttempts: [
        () => Future<String?>.error(Exception('load failed')),
        () => Future<String?>.value('user_recovered'),
      ],
    );
    final state = SessionState(userStorage: storage);
    await Future<void>.delayed(Duration.zero);

    await state.retryUserIdLoad();

    expect(state.userIdLoadState, UserIdLoadState.loaded);
    expect(state.userId, 'user_recovered');
    expect(state.storageErrorMessage, isNull);
    expect(storage.loadCalls, 2);
  });

  test('retry succeeds when no stored user ID exists', () async {
    final storage = FakeUserStorage(
      loadAttempts: [
        () => Future<String?>.error(Exception('load failed')),
        () => Future<String?>.value(null),
      ],
    );
    final state = SessionState(userStorage: storage);
    await Future<void>.delayed(Duration.zero);

    await state.retryUserIdLoad();

    expect(state.userIdLoadState, UserIdLoadState.loaded);
    expect(state.userId, isNull);
    expect(state.storageErrorMessage, isNull);
  });

  test('a failed retry keeps session start blocked', () async {
    var requests = 0;
    final storage = FakeUserStorage(
      loadAttempts: [
        () => Future<String?>.error(Exception('initial failure')),
        () => Future<String?>.error(Exception('retry failure')),
      ],
    );
    final state = SessionState(
      userStorage: storage,
      apiClient: FairiesApiClient(
        client: MockClient((_) async {
          requests += 1;
          return jsonResponse({}, 500);
        }),
      ),
    );
    await Future<void>.delayed(Duration.zero);

    await state.retryUserIdLoad();
    await state.startSession();

    expect(state.userIdLoadState, UserIdLoadState.failed);
    expect(requests, 0);
  });

  test('session start stays blocked while a retry is incomplete', () async {
    final retryLoad = Completer<String?>();
    var requests = 0;
    final storage = FakeUserStorage(
      loadAttempts: [
        () => Future<String?>.error(Exception('initial failure')),
        () => retryLoad.future,
      ],
    );
    final state = SessionState(
      userStorage: storage,
      apiClient: FairiesApiClient(
        client: MockClient((_) async {
          requests += 1;
          return jsonResponse({
            'user_id': 'user_recovered',
            'session_id': 'session_recovered',
            'message': {'role': 'assistant', 'content': '挨拶'},
          }, 201);
        }),
      ),
    );
    await Future<void>.delayed(Duration.zero);

    final retrying = state.retryUserIdLoad();
    await Future<void>.delayed(Duration.zero);
    expect(state.userIdLoadState, UserIdLoadState.loading);
    await state.startSession();
    expect(requests, 0);

    retryLoad.complete('user_recovered');
    await retrying;
    expect(state.userIdLoadState, UserIdLoadState.loaded);
    expect(requests, 0);

    await state.startSession();
    expect(requests, 1);
  });

  test('duplicate user ID retries are ignored while loading', () async {
    final retryLoad = Completer<String?>();
    final storage = FakeUserStorage(
      loadAttempts: [
        () => Future<String?>.error(Exception('initial failure')),
        () => retryLoad.future,
      ],
    );
    final state = SessionState(userStorage: storage);
    await Future<void>.delayed(Duration.zero);

    final first = state.retryUserIdLoad();
    await state.retryUserIdLoad();
    expect(storage.loadCalls, 2);

    retryLoad.complete(null);
    await first;
    expect(state.userIdLoadState, UserIdLoadState.loaded);
  });

  test('new session replaces session ID, messages and match only', () async {
    var attempt = 0;
    final storage = FakeUserStorage(value: 'user_same');
    final state = SessionState(
      userStorage: storage,
      apiClient: FairiesApiClient(
        client: MockClient((_) async {
          attempt += 1;
          return jsonResponse({
            'user_id': 'user_same',
            'session_id': 'session_$attempt',
            'message': {'role': 'assistant', 'content': '挨拶$attempt'},
          }, 201);
        }),
      ),
    );
    await waitForUserIdLoad(state);
    await state.startSession();
    state.messages.add(const ChatMessage(role: 'user', content: '前回の発言'));
    state.matchResponse = MatchResponse.fromJson(_matchJson());

    await state.startSession();

    expect(state.userId, 'user_same');
    expect(state.sessionId, 'session_2');
    expect(state.messages, hasLength(1));
    expect(state.messages.single.content, '挨拶2');
    expect(state.matchResponse, isNull);
  });

  test('save failure keeps the successful current session', () async {
    final storage = FakeUserStorage(failSave: true);
    final state = SessionState(
      userStorage: storage,
      apiClient: FairiesApiClient(
        client: MockClient(
          (_) async => jsonResponse({
            'user_id': 'user_unsaved',
            'session_id': 'session_valid',
            'message': {'role': 'assistant', 'content': '利用可能な挨拶'},
          }, 201),
        ),
      ),
    );

    await waitForUserIdLoad(state);
    await state.startSession();

    expect(state.userId, 'user_unsaved');
    expect(state.sessionId, 'session_valid');
    expect(state.messages.single.content, '利用可能な挨拶');
    expect(state.storageErrorCode, 'USER_ID_SAVE_FAILED');
    expect(state.errorCode, isNull);
  });

  test(
    'does not request a session until stored ID loading completes',
    () async {
      final load = Completer<String?>();
      var requests = 0;
      final state = SessionState(
        userStorage: FakeUserStorage(loadCompleter: load),
        apiClient: FairiesApiClient(
          client: MockClient((_) async {
            requests += 1;
            return jsonResponse({
              'user_id': 'user_delayed',
              'session_id': 'session_delayed',
              'message': {'role': 'assistant', 'content': '挨拶'},
            }, 201);
          }),
        ),
      );

      await state.startSession();
      await Future<void>.delayed(Duration.zero);
      expect(state.isUserStorageReady, isFalse);
      expect(requests, 0);

      load.complete('user_delayed');
      await Future<void>.delayed(Duration.zero);
      expect(state.isUserStorageReady, isTrue);
      expect(requests, 0);

      await state.startSession();
      expect(requests, 1);
    },
  );
}

Future<void> waitForUserIdLoad(SessionState state) async {
  while (state.isUserIdLoading) {
    await Future<void>.delayed(Duration.zero);
  }
}

class FakeUserStorage implements UserStorage {
  FakeUserStorage({
    this.value,
    this.failSave = false,
    this.loadCompleter,
    this.loadAttempts,
  });

  String? value;
  final bool failSave;
  final Completer<String?>? loadCompleter;
  final List<Future<String?> Function()>? loadAttempts;
  final List<String> savedValues = [];
  int loadCalls = 0;

  @override
  Future<String?> loadUserId() {
    final attempt = loadCalls++;
    if (loadAttempts != null && attempt < loadAttempts!.length) {
      return loadAttempts![attempt]();
    }
    return loadCompleter?.future ?? Future.value(value);
  }

  @override
  Future<void> saveUserId(String userId) async {
    if (failSave) throw const UserStorageException('save failed');
    value = userId;
    savedValues.add(userId);
  }

  @override
  Future<void> clearUserId() async => value = null;
}

SessionState _endReadyState(MockClient client) {
  final state = _matchReadyState(client);
  state.matchResponse = MatchResponse.fromJson(_matchJson());
  state.userId = 'user_end';
  state.sessionId = 'session_end';
  return state;
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

http.Response matchStreamResponse(Map<String, dynamic> result) =>
    ndjsonResponse([
      {'type': 'progress', 'phase': 'analyzing'},
      {'type': 'progress', 'phase': 'matching'},
      {'type': 'progress', 'phase': 'memorizing'},
      {'type': 'result', 'data': result},
    ]);

http.Response ndjsonResponse(List<Map<String, dynamic>> events) =>
    http.Response.bytes(
      utf8.encode([...events.map(jsonEncode), ''].join('\n')),
      200,
      headers: {'content-type': 'application/x-ndjson'},
    );
