class ChatMessage {
  const ChatMessage({required this.role, required this.content});

  final String role;
  final String content;

  factory ChatMessage.fromJson(Map<String, dynamic> json) {
    final role = json['role'];
    final content = json['content'];
    if (role is! String || content is! String || content.isEmpty) {
      throw const FormatException('Invalid chat message response.');
    }
    return ChatMessage(role: role, content: content);
  }

  Map<String, dynamic> toJson() => {'role': role, 'content': content};
}
