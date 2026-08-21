import 'package:fairies_app/models/chat_message.dart';
import 'package:fairies_app/models/session.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('ChatMessage parses JSON', () {
    final message = ChatMessage.fromJson({
      'role': 'assistant',
      'content': 'こんにちは',
    });

    expect(message.role, 'assistant');
    expect(message.content, 'こんにちは');
    expect(message.toJson(), {'role': 'assistant', 'content': 'こんにちは'});
  });

  test('Session converts snake_case response to camelCase fields', () {
    final session = Session.fromJson({
      'user_id': 'user_123',
      'session_id': 'session_456',
      'message': {'role': 'assistant', 'content': 'はじめまして'},
    });

    expect(session.userId, 'user_123');
    expect(session.sessionId, 'session_456');
    expect(session.initialMessage.content, 'はじめまして');
  });
}
