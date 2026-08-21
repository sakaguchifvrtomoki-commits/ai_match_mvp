import 'package:flutter/foundation.dart';

import '../models/chat_message.dart';
import '../models/match_response.dart';
import '../services/fairies_api_client.dart';

class SessionState extends ChangeNotifier {
  SessionState({FairiesApiClient? apiClient})
    : _apiClient = apiClient ?? FairiesApiClient();

  final FairiesApiClient _apiClient;

  String? userId;
  String? sessionId;
  final List<ChatMessage> messages = [];
  bool isLoading = false;
  bool isMatching = false;
  MatchResponse? matchResponse;
  String? errorCode;
  String? errorMessage;
  bool _canRetryLastChat = false;

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
      !_canRetryLastChat;

  Future<void> startSession({
    String? existingUserId,
    bool logConsent = true,
  }) async {
    if (isLoading || isMatching) {
      return;
    }
    isLoading = true;
    errorCode = null;
    errorMessage = null;
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
      matchResponse = null;
    } on FairiesApiException catch (error) {
      errorCode = error.code;
      errorMessage = error.message;
    } finally {
      isLoading = false;
      notifyListeners();
    }
  }

  Future<void> sendMessage(String text) async {
    final content = text.trim();
    if (content.isEmpty ||
        !hasSession ||
        isLoading ||
        isMatching ||
        _canRetryLastChat) {
      return;
    }
    messages.add(ChatMessage(role: 'user', content: content));
    _canRetryLastChat = true;
    await _sendCurrentChat();
  }

  Future<void> retryLastChat() async {
    if (!_canRetryLastChat || !hasSession || isLoading || isMatching) {
      return;
    }
    await _sendCurrentChat();
  }

  Future<void> generateMatch() async {
    if (!canMatch) return;

    isMatching = true;
    errorCode = null;
    errorMessage = null;
    notifyListeners();
    try {
      matchResponse = await _apiClient.generateMatch(
        userId: userId!,
        sessionId: sessionId!,
        messages: List.unmodifiable(messages),
      );
    } on FairiesApiException catch (error) {
      errorCode = error.code;
      errorMessage = error.message;
    } finally {
      isMatching = false;
      notifyListeners();
    }
  }

  Future<void> _sendCurrentChat() async {
    isLoading = true;
    errorCode = null;
    errorMessage = null;
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
