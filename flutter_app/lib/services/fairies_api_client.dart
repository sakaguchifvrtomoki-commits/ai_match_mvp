import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../models/chat_message.dart';
import '../models/match_response.dart';
import '../models/session.dart';

class FairiesApiException implements Exception {
  const FairiesApiException({
    required this.code,
    required this.message,
    this.statusCode,
  });

  final String code;
  final String message;
  final int? statusCode;

  @override
  String toString() => 'FairiesApiException($code, status: $statusCode)';
}

class FairiesApiClient {
  FairiesApiClient({http.Client? client, String baseUrl = ApiConfig.baseUrl})
    : _client = client ?? http.Client(),
      _ownsClient = client == null,
      _baseUri = Uri.parse(baseUrl);

  final http.Client _client;
  final bool _ownsClient;
  final Uri _baseUri;

  Future<Session> startSession({
    required String? userId,
    required bool logConsent,
  }) async {
    final response = await _postJson(
      '/sessions',
      body: {'user_id': userId, 'log_consent': logConsent},
    );
    if (response.statusCode != 201) {
      throw _apiError(response, fallbackMessage: 'セッションを開始できませんでした。再試行してください。');
    }
    try {
      return Session.fromJson(_decodeObject(response));
    } on FormatException {
      throw FairiesApiException(
        code: 'INVALID_RESPONSE',
        message: 'サーバーから正しい応答を受け取れませんでした。',
        statusCode: response.statusCode,
      );
    }
  }

  Future<ChatMessage> sendChat({
    required String userId,
    required String sessionId,
    required List<ChatMessage> messages,
  }) async {
    final response = await _postJson(
      '/chat',
      body: {
        'user_id': userId,
        'session_id': sessionId,
        'messages': messages.map((message) => message.toJson()).toList(),
      },
    );
    if (response.statusCode != 200) {
      throw _apiError(
        response,
        fallbackMessage: 'Fairyから応答を取得できませんでした。再試行してください。',
      );
    }
    try {
      final body = _decodeObject(response);
      final message = body['message'];
      if (message is! Map<String, dynamic>) {
        throw const FormatException('Invalid chat response.');
      }
      return ChatMessage.fromJson(message);
    } on FormatException {
      throw FairiesApiException(
        code: 'INVALID_RESPONSE',
        message: 'サーバーから正しい応答を受け取れませんでした。',
        statusCode: response.statusCode,
      );
    }
  }

  Future<MatchResponse> generateMatch({
    required String userId,
    required String sessionId,
    required List<ChatMessage> messages,
  }) async {
    final response = await _postJson(
      '/match',
      body: {
        'user_id': userId,
        'session_id': sessionId,
        'messages': messages.map((message) => message.toJson()).toList(),
      },
    );
    if (response.statusCode != 200) {
      throw _apiError(
        response,
        fallbackMessage: 'マッチング結果を取得できませんでした。再試行してください。',
      );
    }
    try {
      return MatchResponse.fromJson(_decodeObject(response));
    } on FormatException {
      throw FairiesApiException(
        code: 'INVALID_RESPONSE',
        message: 'サーバーから正しい応答を受け取れませんでした。',
        statusCode: response.statusCode,
      );
    }
  }

  Future<http.Response> _postJson(
    String path, {
    required Map<String, dynamic> body,
  }) async {
    try {
      return await _client.post(
        _baseUri.resolve(path),
        headers: {'Content-Type': 'application/json; charset=utf-8'},
        body: jsonEncode(body),
      );
    } catch (_) {
      throw const FairiesApiException(
        code: 'NETWORK_ERROR',
        message: 'サーバーに接続できませんでした。時間をおいて再試行してください。',
      );
    }
  }

  Map<String, dynamic> _decodeObject(http.Response response) {
    final decoded = jsonDecode(utf8.decode(response.bodyBytes));
    if (decoded is! Map<String, dynamic>) {
      throw const FormatException('Expected a JSON object.');
    }
    return decoded;
  }

  FairiesApiException _apiError(
    http.Response response, {
    required String fallbackMessage,
  }) {
    try {
      final body = _decodeObject(response);
      final error = body['error'];
      if (error is Map<String, dynamic> &&
          error['code'] is String &&
          error['message'] is String) {
        return FairiesApiException(
          code: error['code'] as String,
          message: error['message'] as String,
          statusCode: response.statusCode,
        );
      }
    } catch (_) {
      // Fall through to a retryable generic server error.
    }
    return FairiesApiException(
      code: 'HTTP_ERROR',
      message: fallbackMessage,
      statusCode: response.statusCode,
    );
  }

  void close() {
    if (_ownsClient) {
      _client.close();
    }
  }
}
