import 'chat_message.dart';

class Session {
  const Session({
    required this.userId,
    required this.sessionId,
    required this.initialMessage,
  });

  final String userId;
  final String sessionId;
  final ChatMessage initialMessage;

  factory Session.fromJson(Map<String, dynamic> json) {
    final userId = json['user_id'];
    final sessionId = json['session_id'];
    final message = json['message'];
    if (userId is! String ||
        userId.isEmpty ||
        sessionId is! String ||
        sessionId.isEmpty ||
        message is! Map<String, dynamic>) {
      throw const FormatException('Invalid session response.');
    }
    return Session(
      userId: userId,
      sessionId: sessionId,
      initialMessage: ChatMessage.fromJson(message),
    );
  }
}
