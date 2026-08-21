import 'package:flutter/material.dart';

import '../models/chat_message.dart';
import '../models/match_response.dart';
import '../state/session_state.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, this.sessionState});

  final SessionState? sessionState;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late final SessionState _sessionState;
  late final bool _ownsSessionState;
  final TextEditingController _messageController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _ownsSessionState = widget.sessionState == null;
    _sessionState = widget.sessionState ?? SessionState();
  }

  @override
  void dispose() {
    _messageController.dispose();
    if (_ownsSessionState) {
      _sessionState.dispose();
    }
    super.dispose();
  }

  Future<void> _sendMessage() async {
    final text = _messageController.text;
    await _sessionState.sendMessage(text);
    if (_sessionState.errorMessage == null && !_sessionState.canRetryLastChat) {
      _messageController.clear();
    }
  }

  Future<void> _retryChat() async {
    await _sessionState.retryLastChat();
    if (_sessionState.errorMessage == null && !_sessionState.canRetryLastChat) {
      _messageController.clear();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('フェアリーズ')),
      body: SafeArea(
        child: AnimatedBuilder(
          animation: _sessionState,
          builder: (context, child) {
            if (!_sessionState.hasSession) {
              return _SessionStart(
                state: _sessionState,
                onStart: _sessionState.startSession,
              );
            }
            return Column(
              children: [
                Expanded(
                  child: ListView.builder(
                    key: const Key('conversation-list'),
                    padding: const EdgeInsets.all(16),
                    itemCount:
                        _sessionState.messages.length +
                        (_sessionState.matchResponse == null ? 0 : 1),
                    itemBuilder: (context, index) {
                      if (index == _sessionState.messages.length) {
                        return _MatchResultCard(
                          response: _sessionState.matchResponse!,
                        );
                      }
                      return _MessageBubble(
                        message: _sessionState.messages[index],
                      );
                    },
                  ),
                ),
                if (_sessionState.isLoading)
                  const LinearProgressIndicator(key: Key('chat-loading')),
                if (_sessionState.isMatching)
                  const LinearProgressIndicator(key: Key('match-loading')),
                if (_sessionState.isEnding)
                  const LinearProgressIndicator(key: Key('end-loading')),
                if (_sessionState.errorMessage != null)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(
                          _sessionState.errorMessage!,
                          key: const Key('chat-error'),
                          style: TextStyle(
                            color: Theme.of(context).colorScheme.error,
                          ),
                        ),
                        if (_sessionState.canRetryLastChat)
                          TextButton(
                            key: const Key('retry-chat'),
                            onPressed: _sessionState.isLoading
                                ? null
                                : _retryChat,
                            child: const Text('再試行'),
                          ),
                      ],
                    ),
                  ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
                  child: Wrap(
                    alignment: WrapAlignment.spaceBetween,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      Text('ユーザー発言 ${_sessionState.userMessageCount}/3件以上'),
                      FilledButton.icon(
                        key: const Key('generate-match'),
                        onPressed: _sessionState.canMatch
                            ? _sessionState.generateMatch
                            : null,
                        icon: const Icon(Icons.favorite),
                        label: Text(
                          _sessionState.isMatching ? 'マッチング中' : 'マッチングする',
                        ),
                      ),
                      OutlinedButton.icon(
                        key: const Key('end-session'),
                        onPressed: _sessionState.canEndSession
                            ? _sessionState.endSession
                            : null,
                        icon: const Icon(Icons.stop_circle_outlined),
                        label: Text(
                          _sessionState.isEnding ? '終了処理中' : 'セッションを終了',
                        ),
                      ),
                    ],
                  ),
                ),
                if (_sessionState.isSessionCompleted)
                  const Padding(
                    padding: EdgeInsets.fromLTRB(12, 8, 12, 0),
                    child: Text('セッションを終了しました', key: Key('session-completed')),
                  ),
                Padding(
                  padding: const EdgeInsets.all(12),
                  child: Row(
                    children: [
                      Expanded(
                        child: TextField(
                          key: const Key('chat-input'),
                          controller: _messageController,
                          enabled:
                              !_sessionState.isLoading &&
                              !_sessionState.isMatching &&
                              !_sessionState.isEnding &&
                              !_sessionState.isSessionCompleted &&
                              !_sessionState.canRetryLastChat,
                          minLines: 1,
                          maxLines: 4,
                          textInputAction: TextInputAction.send,
                          onSubmitted: (_) => _sendMessage(),
                          decoration: const InputDecoration(
                            hintText: 'メッセージを入力',
                            border: OutlineInputBorder(),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      IconButton.filled(
                        key: const Key('send-chat'),
                        onPressed:
                            _sessionState.isLoading ||
                                _sessionState.isMatching ||
                                _sessionState.isEnding ||
                                _sessionState.isSessionCompleted ||
                                _sessionState.canRetryLastChat
                            ? null
                            : _sendMessage,
                        icon: const Icon(Icons.send),
                        tooltip: '送信',
                      ),
                    ],
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _MatchResultCard extends StatelessWidget {
  const _MatchResultCard({required this.response});

  final MatchResponse response;

  @override
  Widget build(BuildContext context) {
    final result = response.match;
    final candidate = result.matchedCandidate;
    final support = response.afterMatchSupport;
    return Card(
      key: const Key('match-result'),
      margin: const EdgeInsets.only(top: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('分析: ${response.analysis.summary}'),
            const SizedBox(height: 8),
            Text('${candidate.name}（${candidate.age}歳）'),
            Text('相性: ${result.matchScore}点・${result.matchLabel}'),
            Text('理由: ${result.matchReason}'),
            Text('気になる点: ${result.possibleConcern}'),
            Text('最初のメッセージ: ${result.recommendedFirstMessage}'),
            Text('プロフィール更新: ${response.profileUpdated ? '成功' : '失敗'}'),
            if (support != null) ...[
              const Divider(),
              Text('今日の一言: ${support.firstMessageToday}'),
              Text('3日後の質問: ${support.questionIn3days}'),
              Text('避けたい表現: ${support.avoidPhrase}'),
              Text('返信が遅い時: ${support.slowReplyAction}'),
            ],
          ],
        ),
      ),
    );
  }
}

class _SessionStart extends StatelessWidget {
  const _SessionStart({required this.state, required this.onStart});

  final SessionState state;
  final VoidCallback onStart;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 520),
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (state.isLoading)
                const Center(child: CircularProgressIndicator())
              else ...[
                if (state.errorMessage != null) ...[
                  Text(
                    state.errorMessage!,
                    key: const Key('session-error'),
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                  const SizedBox(height: 12),
                ],
                FilledButton(
                  onPressed: onStart,
                  child: Text(state.errorMessage == null ? 'セッションを開始' : '再試行'),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({required this.message});

  final ChatMessage message;

  @override
  Widget build(BuildContext context) {
    final isUser = message.role == 'user';
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        key: Key('message-${message.role}'),
        constraints: const BoxConstraints(maxWidth: 360),
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: isUser
              ? Theme.of(context).colorScheme.primaryContainer
              : Theme.of(context).colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Text(message.content),
      ),
    );
  }
}
