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
