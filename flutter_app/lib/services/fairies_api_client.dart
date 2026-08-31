import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../models/chat_message.dart';
import '../models/match_response.dart';
import '../models/match_loading_phase.dart';
import '../models/session.dart';
import '../models/session_end_response.dart';

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
      final body = _decodeObject(response);
      return MatchResponse.fromJson(body);
    } on FormatException {
      throw FairiesApiException(
        code: 'INVALID_RESPONSE',
        message: 'サーバーから正しい応答を受け取れませんでした。',
        statusCode: response.statusCode,
      );
    }
  }

  Future<MatchResponse> generateMatchStream({
    required String userId,
    required String sessionId,
    required List<ChatMessage> messages,
    required void Function(MatchLoadingPhase phase) onProgress,
  }) async {
    final request = http.Request('POST', _baseUri.resolve('/match/stream'))
      ..headers['Content-Type'] = 'application/json; charset=utf-8'
      ..body = jsonEncode({
        'user_id': userId,
        'session_id': sessionId,
        'messages': messages.map((message) => message.toJson()).toList(),
      });

    late http.StreamedResponse response;
    try {
      response = await _client.send(request);
    } catch (_) {
      throw const FairiesApiException(
        code: 'NETWORK_ERROR',
        message: 'サーバーに接続できませんでした。時間をおいて再試行してください。',
      );
    }

    if (response.statusCode != 200) {
      final bodyBytes = await response.stream.toBytes();
      throw _apiError(
        http.Response.bytes(
          bodyBytes,
          response.statusCode,
          headers: response.headers,
        ),
        fallbackMessage: 'マッチング結果を取得できませんでした。再試行してください。',
      );
    }

    try {
      await for (final line
          in response.stream
              .transform(utf8.decoder)
              .transform(const LineSplitter())) {
        if (line.trim().isEmpty) continue;
        final decoded = jsonDecode(line);
        if (decoded is! Map<String, dynamic> || decoded['type'] is! String) {
          throw const FormatException('Invalid match stream event.');
        }
        switch (decoded['type']) {
          case 'progress':
            final rawPhase = decoded['phase'];
            if (rawPhase is! String) {
              throw const FormatException('Invalid progress event.');
            }
            final phase = matchLoadingPhaseFromApi(rawPhase);
            if (phase != null) onProgress(phase);
            continue;
          case 'result':
            final data = decoded['data'];
            if (data is! Map<String, dynamic>) {
              throw const FormatException('Invalid result event.');
            }
            return MatchResponse.fromJson(data);
          case 'error':
            final error = decoded['error'];
            if (error is! Map<String, dynamic> ||
                error['code'] is! String ||
                error['message'] is! String) {
              throw const FormatException('Invalid error event.');
            }
            throw FairiesApiException(
              code: error['code'] as String,
              message: error['message'] as String,
              statusCode: response.statusCode,
            );
          default:
            throw const FormatException('Unknown match stream event.');
        }
      }
    } on FairiesApiException {
      rethrow;
    } on FormatException {
      throw const FairiesApiException(
        code: 'INVALID_RESPONSE',
        message: 'サーバーから正しい応答を受け取れませんでした。',
      );
    } catch (_) {
      throw const FairiesApiException(
        code: 'NETWORK_ERROR',
        message: 'サーバーとの通信が切断されました。再試行してください。',
      );
    }

    throw const FairiesApiException(
      code: 'INVALID_RESPONSE',
      message: 'サーバーからマッチング結果を受け取れませんでした。',
    );
  }

  Future<SessionEndResponse> endSession({
    required String userId,
    required String sessionId,
    required List<ChatMessage> messages,
    MatchResponse? matchResponse,
  }) async {
    final response = await _postJson(
      '/sessions/${Uri.encodeComponent(sessionId)}/end',
      body: {
        'user_id': userId,
        'messages': messages.map((message) => message.toJson()).toList(),
        'analysis': matchResponse?.analysis.toJson(),
        'match': matchResponse?.match.toJson(),
        'top_candidates':
            matchResponse?.topCandidates
                .map((candidate) => candidate.toJson())
                .toList() ??
            [],
        'after_match_support': matchResponse?.afterMatchSupport?.toJson(),
      },
    );
    if (response.statusCode != 200) {
      throw _apiError(response, fallbackMessage: 'セッションを終了できませんでした。再試行してください。');
    }
    try {
      return SessionEndResponse.fromJson(_decodeObject(response));
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
