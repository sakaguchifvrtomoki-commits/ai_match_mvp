import 'package:flutter/foundation.dart';

import '../models/chat_message.dart';
import '../services/fairies_api_client.dart';

class SessionState extends ChangeNotifier {
  SessionState({FairiesApiClient? apiClient})
    : _apiClient = apiClient ?? FairiesApiClient();

  final FairiesApiClient _apiClient;

  String? userId;
  String? sessionId;
  final List<ChatMessage> messages = [];
  bool isLoading = false;
  String? errorCode;
  String? errorMessage;
  bool _canRetryLastChat = false;

  bool get hasSession => userId != null && sessionId != null;
  bool get canRetryLastChat => _canRetryLastChat;

  Future<void> startSession({
    String? existingUserId,
    bool logConsent = true,
  }) async {
    if (isLoading) {
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
    if (content.isEmpty || !hasSession || isLoading || _canRetryLastChat) {
      return;
    }
    messages.add(ChatMessage(role: 'user', content: content));
    _canRetryLastChat = true;
    await _sendCurrentChat();
  }

  Future<void> retryLastChat() async {
    if (!_canRetryLastChat || !hasSession || isLoading) {
      return;
    }
    await _sendCurrentChat();
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
