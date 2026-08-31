import 'package:flutter/foundation.dart';

import '../models/chat_message.dart';
import '../models/match_response.dart';
import '../models/match_loading_phase.dart';
import '../services/fairies_api_client.dart';
import '../services/user_storage.dart';

enum SessionErrorAction { sessionStart, chat, match, end }

class SessionState extends ChangeNotifier {
  SessionState({FairiesApiClient? apiClient, UserStorage? userStorage})
    : _apiClient = apiClient ?? FairiesApiClient(),
      _userStorage = userStorage ?? const SharedPreferencesUserStorage() {
    _userStorageInitialization = _loadStoredUserId();
  }

  final FairiesApiClient _apiClient;
  final UserStorage _userStorage;
  late final Future<void> _userStorageInitialization;

  String? userId;
  String? sessionId;
  final List<ChatMessage> messages = [];
  bool isLoading = false;
  bool isMatching = false;
  MatchLoadingPhase? matchLoadingPhase;
  bool isEnding = false;
  bool isSessionCompleted = false;
  MatchResponse? matchResponse;
  String? errorCode;
  String? errorMessage;
  SessionErrorAction? errorAction;
  bool isUserStorageReady = false;
  String? storageErrorCode;
  String? storageErrorMessage;
  bool _canRetryLastChat = false;
  int? _lastMatchedUserMessageCount;

  bool get hasSession => userId != null && sessionId != null;
  bool get canRetryLastChat => _canRetryLastChat;
  int get userMessageCount => messages
      .where(
        (message) =>
            message.role == 'user' && message.content.trim().isNotEmpty,
      )
      .length;
  bool get canMatch =>
      hasSession &&
      userMessageCount >= 3 &&
      !isLoading &&
      !isMatching &&
      !isEnding &&
      !isSessionCompleted &&
      !_canRetryLastChat &&
      matchResponse == null &&
      (_lastMatchedUserMessageCount == null ||
          userMessageCount > _lastMatchedUserMessageCount!);
  bool get canEndSession =>
      hasSession &&
      !isLoading &&
      !isMatching &&
      !isEnding &&
      !isSessionCompleted;

  Future<void> startSession({
    String? existingUserId,
    bool logConsent = true,
  }) async {
    await _userStorageInitialization;
    if (isLoading || isMatching || isEnding) return;
    isLoading = true;
    errorCode = null;
    errorMessage = null;
    errorAction = null;
    notifyListeners();

    try {
      final session = await _apiClient.startSession(
        userId: existingUserId ?? userId,
        logConsent: logConsent,
      );
      userId = session.userId;
      sessionId = session.sessionId;
      messages
        ..clear()
        ..add(session.initialMessage);
      _canRetryLastChat = false;
      _lastMatchedUserMessageCount = null;
      matchResponse = null;
      isSessionCompleted = false;
      try {
        await _userStorage.saveUserId(session.userId);
        storageErrorCode = null;
        storageErrorMessage = null;
      } catch (_) {
        storageErrorCode = 'USER_ID_SAVE_FAILED';
        storageErrorMessage = 'ユーザー情報を端末に保存できませんでした。現在のセッションは利用できます。';
      }
    } on FairiesApiException catch (error) {
      errorCode = error.code;
      errorMessage = error.message;
      errorAction = SessionErrorAction.sessionStart;
    } finally {
      isLoading = false;
      notifyListeners();
    }
  }

  Future<void> _loadStoredUserId() async {
    try {
      final storedUserId = await _userStorage.loadUserId();
      userId ??= storedUserId;
    } catch (_) {
      storageErrorCode = 'USER_ID_LOAD_FAILED';
      storageErrorMessage = '保存済みのユーザー情報を読み込めませんでした。';
    } finally {
      isUserStorageReady = true;
      notifyListeners();
    }
  }

  Future<void> sendMessage(String text) async {
    final content = text.trim();
    if (content.isEmpty ||
        !hasSession ||
        isLoading ||
        isMatching ||
        isEnding ||
        isSessionCompleted ||
        matchResponse != null ||
        _canRetryLastChat) {
      return;
    }
    messages.add(ChatMessage(role: 'user', content: content));
    _canRetryLastChat = true;
    await _sendCurrentChat();
  }

  Future<void> retryLastChat() async {
    if (!_canRetryLastChat ||
        !hasSession ||
        isLoading ||
        isMatching ||
        isEnding ||
        isSessionCompleted) {
      return;
    }
    await _sendCurrentChat();
  }

  Future<void> generateMatch() async {
    if (!canMatch) return;

    isMatching = true;
    matchLoadingPhase = MatchLoadingPhase.analyzing;
    errorCode = null;
    errorMessage = null;
    errorAction = null;
    notifyListeners();
    try {
      final response = await _apiClient.generateMatchStream(
        userId: userId!,
        sessionId: sessionId!,
        messages: List.unmodifiable(messages),
        onProgress: (phase) {
          matchLoadingPhase = phase;
          notifyListeners();
        },
      );
      matchResponse = response;
      _lastMatchedUserMessageCount = userMessageCount;
    } on FairiesApiException catch (error) {
      errorCode = error.code;
      errorMessage = error.message;
      errorAction = SessionErrorAction.match;
    } finally {
      isMatching = false;
      matchLoadingPhase = null;
      notifyListeners();
    }
  }

  Future<void> endSession() async {
    if (!canEndSession) return;

    isEnding = true;
    errorCode = null;
    errorMessage = null;
    errorAction = null;
    notifyListeners();
    try {
      final response = await _apiClient.endSession(
        userId: userId!,
        sessionId: sessionId!,
        messages: List.unmodifiable(messages),
        matchResponse: matchResponse,
      );
      isSessionCompleted = response.status == 'completed';
    } on FairiesApiException catch (error) {
      errorCode = error.code;
      errorMessage = error.message;
      errorAction = SessionErrorAction.end;
    } finally {
      isEnding = false;
      notifyListeners();
    }
  }

  bool prepareForNewSession() {
    if (isLoading || isMatching || isEnding) return false;

    sessionId = null;
    messages.clear();
    matchResponse = null;
    matchLoadingPhase = null;
    isSessionCompleted = false;
    errorCode = null;
    errorMessage = null;
    errorAction = null;
    _canRetryLastChat = false;
    _lastMatchedUserMessageCount = null;
    notifyListeners();
    return true;
  }

  bool resumeConversationAfterMatch() {
    if (matchResponse == null || isLoading || isMatching || isEnding) {
      return false;
    }
    matchResponse = null;
    errorCode = null;
    errorMessage = null;
    errorAction = null;
    notifyListeners();
    return true;
  }

  Future<void> _sendCurrentChat() async {
    isLoading = true;
    errorCode = null;
    errorMessage = null;
    errorAction = null;
    notifyListeners();

    try {
      final reply = await _apiClient.sendChat(
        userId: userId!,
        sessionId: sessionId!,
        messages: List.unmodifiable(messages),
      );
      messages.add(reply);
      _canRetryLastChat = false;
    } on FairiesApiException catch (error) {
      errorCode = error.code;
      errorMessage = error.message;
      errorAction = SessionErrorAction.chat;
    } finally {
      isLoading = false;
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _apiClient.close();
    super.dispose();
  }
}
