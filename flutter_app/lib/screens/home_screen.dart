import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/chat_message.dart';
import '../models/match_loading_phase.dart';
import '../models/match_response.dart';
import '../state/session_state.dart';

const fairiesAppVersion = 'v0.2.2';
const fairiesSurveyUrl =
    'https://docs.google.com/forms/d/e/1FAIpQLSeEl3FGWUk_-B7CtGLBOq1YNeeRNcClNibd-8ikF_Weh6rE9A/viewform';

// Visual tuning constants. Change one value and hot reload to compare on-device.
const _backgroundOverlayColor = Color(0x44FFFFFF);
const _appBarColor = Color(0xD95A3F82);
const _appBarTextColor = Colors.white;
const _primaryButtonColor = Color(0xFF6D4AA2);
const _primaryButtonTextColor = Colors.white;
const _fairyBubbleColor = Color(0xF2FFFFFF);
const _userBubbleColor = Color(0xE8D9CCF3);
const _fairyBubbleTextColor = Color(0xFF2D2638);
const _userBubbleTextColor = Color(0xFF2F2144);
const _chatBubbleMaxWidthRatio = 0.78;
const _chatBubbleRadius = 18.0;
const _chatBubbleHorizontalPadding = 14.0;
const _chatBubbleVerticalPadding = 10.0;
const _inputFillColor = Color(0xF2FFFFFF);
const _loadingBackgroundColor = Color(0xEFFFFFFF);

const _analysisSectionColor = Color(0xFFEDE7F6);
const _matchSectionColor = Color(0xFFFCE4EC);
const _warningSectionColor = Color(0xFFFFE8D6);
const _messageSectionColor = Color(0xFFE3F2FD);
const _otherCandidatesSectionColor = Color(0xFFEDEAF4);
const _supportSectionColor = Color(0xFFE0F2E9);
const _profileSectionColor = Color(0xFFFFF3D6);
const _profileUpdateSectionColor = Color(0xFFF5F3F8);
const _resultSectionTitleColor = Color(0xFF493560);
const _resultSectionBorderColor = Color(0x665E477A);
const _resultSectionOpacity = 0.94;
const _matchResultCardColor = Color(0xF2FFFFFF);
final ButtonStyle _primaryFilledButtonStyle = FilledButton.styleFrom(
  backgroundColor: _primaryButtonColor,
  foregroundColor: _primaryButtonTextColor,
);

typedef SurveyLauncher = Future<bool> Function(Uri uri);

Future<bool> _launchSurveyInBrowser(Uri uri) =>
    launchUrl(uri, mode: LaunchMode.externalApplication);

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, this.sessionState, this.surveyLauncher});

  final SessionState? sessionState;
  final SurveyLauncher? surveyLauncher;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late final SessionState _sessionState;
  late final bool _ownsSessionState;
  final TextEditingController _messageController = TextEditingController();
  final ScrollController _conversationScrollController = ScrollController();
  final GlobalKey _conversationViewportKey = GlobalKey();
  final GlobalKey _matchResultKey = GlobalKey();
  String? _observedSessionId;
  bool? _logConsentChoice;
  bool _showConsentDeclined = false;
  String? _consentValidationMessage;
  bool _surveyChoiceCompleted = false;
  bool _isOpeningSurvey = false;
  String? _surveyErrorMessage;

  @override
  void initState() {
    super.initState();
    _ownsSessionState = widget.sessionState == null;
    _sessionState = widget.sessionState ?? SessionState();
  }

  @override
  void dispose() {
    _messageController.dispose();
    _conversationScrollController.dispose();
    if (_ownsSessionState) {
      _sessionState.dispose();
    }
    super.dispose();
  }

  Future<void> _sendMessage() async {
    final text = _messageController.text;
    final beforeSend = _sessionState.messages.length;
    final sending = _sessionState.sendMessage(text);
    await Future<void>.delayed(Duration.zero);
    final afterUserMessage = _sessionState.messages.length;
    if (afterUserMessage > beforeSend) {
      _scheduleLatestMessageScroll(resetPosition: false);
    }
    await sending;
    if (_sessionState.messages.length > afterUserMessage) {
      _scheduleLatestMessageScroll(resetPosition: false);
    }
    if (_sessionState.errorMessage == null && !_sessionState.canRetryLastChat) {
      _messageController.clear();
    }
  }

  Future<void> _retryChat() async {
    final beforeRetry = _sessionState.messages.length;
    await _sessionState.retryLastChat();
    if (_sessionState.messages.length > beforeRetry) {
      _scheduleLatestMessageScroll(resetPosition: false);
    }
    if (_sessionState.errorMessage == null && !_sessionState.canRetryLastChat) {
      _messageController.clear();
    }
  }

  Future<void> _generateMatch() async {
    final previous = _sessionState.matchResponse;
    await _sessionState.generateMatch();
    if (_sessionState.matchResponse != null &&
        !identical(previous, _sessionState.matchResponse)) {
      _scheduleMatchResultScroll();
    }
  }

  void _resumeConversationAfterMatch() {
    if (!_sessionState.resumeConversationAfterMatch()) return;
    _scheduleLatestMessageScroll(resetPosition: false);
  }

  Future<void> _retryCurrentError() async {
    switch (_sessionState.errorAction) {
      case SessionErrorAction.chat:
        await _retryChat();
      case SessionErrorAction.match:
        await _generateMatch();
      case SessionErrorAction.end:
        await _sessionState.endSession();
      case SessionErrorAction.sessionStart:
        await _continueFromConsent();
      case null:
        return;
    }
  }

  String _errorTitle(SessionErrorAction action) => switch (action) {
    SessionErrorAction.sessionStart => 'Fairyを呼べませんでした',
    SessionErrorAction.chat => 'Fairyから返答を受け取れませんでした',
    SessionErrorAction.match => 'マッチング結果を取得できませんでした',
    SessionErrorAction.end => 'セッションを終了できませんでした',
  };

  Key _errorKey(SessionErrorAction action) => switch (action) {
    SessionErrorAction.sessionStart => const Key('session-error'),
    SessionErrorAction.chat => const Key('chat-error'),
    SessionErrorAction.match => const Key('match-error'),
    SessionErrorAction.end => const Key('end-error'),
  };

  Key _retryKey(SessionErrorAction action) => switch (action) {
    SessionErrorAction.sessionStart => const Key('session-retry'),
    SessionErrorAction.chat => const Key('chat-retry'),
    SessionErrorAction.match => const Key('match-retry'),
    SessionErrorAction.end => const Key('end-retry'),
  };

  void _selectLogConsent(bool consent) {
    setState(() {
      _logConsentChoice = consent;
      _consentValidationMessage = null;
    });
  }

  Future<void> _continueFromConsent() async {
    final consent = _logConsentChoice;
    if (consent == null) {
      setState(() => _consentValidationMessage = '同意するかどうかを選択してください。');
      return;
    }
    if (!consent) {
      setState(() => _showConsentDeclined = true);
      return;
    }
    await _sessionState.startSession(logConsent: consent);
  }

  void _backToConsent() {
    setState(() {
      _showConsentDeclined = false;
      _logConsentChoice = null;
      _consentValidationMessage = null;
    });
  }

  Future<void> _openSurvey() async {
    if (_isOpeningSurvey) return;
    setState(() {
      _isOpeningSurvey = true;
      _surveyErrorMessage = null;
    });
    try {
      final launcher = widget.surveyLauncher ?? _launchSurveyInBrowser;
      final opened = await launcher(Uri.parse(fairiesSurveyUrl));
      if (!mounted) return;
      setState(() {
        _surveyChoiceCompleted = opened;
        if (!opened) {
          _surveyErrorMessage = 'アンケートを開けませんでした。もう一度お試しください。';
        }
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _surveyErrorMessage = 'アンケートを開けませんでした。もう一度お試しください。';
      });
    } finally {
      if (mounted) setState(() => _isOpeningSurvey = false);
    }
  }

  void _skipSurvey() {
    setState(() {
      _surveyChoiceCompleted = true;
      _surveyErrorMessage = null;
    });
  }

  void _prepareNewSession() {
    if (!_sessionState.prepareForNewSession()) return;
    _messageController.clear();
    setState(() {
      _surveyChoiceCompleted = false;
      _surveyErrorMessage = null;
      _showConsentDeclined = false;
      _logConsentChoice = null;
      _consentValidationMessage = null;
    });
  }

  void _requestScrollForContentChanges() {
    final sessionChanged = _observedSessionId != _sessionState.sessionId;

    _observedSessionId = _sessionState.sessionId;

    if (!_sessionState.hasSession) return;
    if (sessionChanged) {
      _scheduleLatestMessageScroll(resetPosition: sessionChanged);
    }
  }

  void _scheduleLatestMessageScroll({required bool resetPosition}) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_conversationScrollController.hasClients) return;
      if (resetPosition) {
        _conversationScrollController.jumpTo(0);
      }
      _conversationScrollController.animateTo(
        _conversationScrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 220),
        curve: Curves.easeOut,
      );
    });
    WidgetsBinding.instance.ensureVisualUpdate();
  }

  void _scheduleMatchResultScroll() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_conversationScrollController.hasClients) return;
      final matchBox =
          _matchResultKey.currentContext?.findRenderObject() as RenderBox?;
      final viewportBox =
          _conversationViewportKey.currentContext?.findRenderObject()
              as RenderBox?;
      if (matchBox == null || viewportBox == null) return;
      final position = _conversationScrollController.position;
      final delta =
          matchBox.localToGlobal(Offset.zero).dy -
          viewportBox.localToGlobal(Offset.zero).dy;
      final target = (position.pixels + delta).clamp(
        position.minScrollExtent,
        position.maxScrollExtent,
      );
      _conversationScrollController.animateTo(
        target,
        duration: const Duration(milliseconds: 260),
        curve: Curves.easeOut,
      );
    });
    WidgetsBinding.instance.ensureVisualUpdate();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: _appBarColor,
        foregroundColor: _appBarTextColor,
        title: const Row(
          children: [
            Text('フェアリーズ'),
            Spacer(),
            Text(fairiesAppVersion, key: Key('app-version')),
          ],
        ),
      ),
      body: DecoratedBox(
        key: const Key('fairies-background'),
        decoration: const BoxDecoration(
          image: DecorationImage(
            image: AssetImage('assets/fairies_ai_BG.png'),
            fit: BoxFit.cover,
            colorFilter: ColorFilter.mode(
              _backgroundOverlayColor,
              BlendMode.srcOver,
            ),
          ),
        ),
        child: SafeArea(
          child: AnimatedBuilder(
            animation: _sessionState,
            builder: (context, child) {
              _requestScrollForContentChanges();
              if (_sessionState.isSessionCompleted) {
                return _SurveyScreen(
                  choiceCompleted: _surveyChoiceCompleted,
                  isOpeningSurvey: _isOpeningSurvey,
                  errorMessage: _surveyErrorMessage,
                  onOpenSurvey: _openSurvey,
                  onSkip: _skipSurvey,
                  onNewSession: _prepareNewSession,
                );
              }
              if (!_sessionState.hasSession) {
                if (_showConsentDeclined) {
                  return _ConsentDeclinedScreen(onBack: _backToConsent);
                }
                return _ConsentScreen(
                  state: _sessionState,
                  selectedConsent: _logConsentChoice,
                  validationMessage: _consentValidationMessage,
                  onConsentChanged: _selectLogConsent,
                  onContinue: _continueFromConsent,
                );
              }
              return Column(
                children: [
                  if (_sessionState.storageErrorMessage != null)
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                      child: Text(
                        _sessionState.storageErrorMessage!,
                        key: const Key('storage-error'),
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.error,
                        ),
                      ),
                    ),
                  Expanded(
                    child: KeyedSubtree(
                      key: _conversationViewportKey,
                      child: ListView.builder(
                        key: const Key('conversation-list'),
                        controller: _conversationScrollController,
                        padding: const EdgeInsets.all(16),
                        itemCount:
                            _sessionState.messages.length +
                            (_sessionState.isLoading ? 1 : 0) +
                            (_sessionState.matchResponse == null ? 0 : 1),
                        itemBuilder: (context, index) {
                          if (index < _sessionState.messages.length) {
                            return _MessageBubble(
                              message: _sessionState.messages[index],
                            );
                          }
                          if (_sessionState.isLoading) {
                            return const _LoadingIndicator(
                              key: Key('chat-loading'),
                              message: 'Fairyが考えています…',
                            );
                          }
                          if (_sessionState.matchResponse != null) {
                            return KeyedSubtree(
                              key: _matchResultKey,
                              child: _MatchResultCard(
                                response: _sessionState.matchResponse!,
                              ),
                            );
                          }
                          return const SizedBox.shrink();
                        },
                      ),
                    ),
                  ),
                  if (_sessionState.isMatching)
                    _LoadingIndicator(
                      key: const Key('match-loading'),
                      message: _matchLoadingMessage(
                        _sessionState.matchLoadingPhase,
                      ),
                    ),
                  if (_sessionState.isEnding)
                    const _LoadingIndicator(
                      key: Key('end-loading'),
                      message: 'セッションを終了しています…',
                    ),
                  if (_sessionState.errorMessage != null &&
                      _sessionState.errorAction != null)
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                      child: _ErrorNotice(
                        key: _errorKey(_sessionState.errorAction!),
                        title: _errorTitle(_sessionState.errorAction!),
                        message: _sessionState.errorMessage!,
                        retryKey: _retryKey(_sessionState.errorAction!),
                        onRetry: _retryCurrentError,
                      ),
                    ),
                  if (_sessionState.matchResponse != null)
                    Padding(
                      padding: const EdgeInsets.all(12),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          FilledButton(
                            key: const Key('resume-conversation'),
                            onPressed: _sessionState.isEnding
                                ? null
                                : _resumeConversationAfterMatch,
                            style: _primaryFilledButtonStyle,
                            child: const Text('もう一度会話する'),
                          ),
                          const SizedBox(height: 8),
                          OutlinedButton.icon(
                            key: const Key('end-session'),
                            onPressed: _sessionState.canEndSession
                                ? _sessionState.endSession
                                : null,
                            icon: const Icon(Icons.stop_circle_outlined),
                            label: Text(
                              _sessionState.isEnding ? '終了処理中' : '終わる',
                            ),
                          ),
                        ],
                      ),
                    )
                  else ...[
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
                                ? _generateMatch
                                : null,
                            style: _primaryFilledButtonStyle,
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
                              keyboardType: TextInputType.multiline,
                              textInputAction: TextInputAction.newline,
                              style: const TextStyle(
                                color: _fairyBubbleTextColor,
                              ),
                              decoration: const InputDecoration(
                                hintText: 'メッセージを入力',
                                border: OutlineInputBorder(),
                                enabledBorder: OutlineInputBorder(
                                  borderSide: BorderSide(
                                    color: _resultSectionBorderColor,
                                  ),
                                ),
                                filled: true,
                                fillColor: _inputFillColor,
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
                ],
              );
            },
          ),
        ),
      ),
    );
  }

  String _matchLoadingMessage(MatchLoadingPhase? phase) {
    return switch (phase) {
      MatchLoadingPhase.analyzing => 'Fairyがあなたを分析しています…',
      MatchLoadingPhase.matching => 'あなたに合いそうな相手を探しています…',
      MatchLoadingPhase.memorizing => 'Fairyが今回の会話を記憶にまとめています…',
      null => 'Fairyがあなたを分析しています…',
    };
  }
}

class _SurveyScreen extends StatelessWidget {
  const _SurveyScreen({
    required this.choiceCompleted,
    required this.isOpeningSurvey,
    required this.errorMessage,
    required this.onOpenSurvey,
    required this.onSkip,
    required this.onNewSession,
  });

  final bool choiceCompleted;
  final bool isOpeningSurvey;
  final String? errorMessage;
  final VoidCallback onOpenSurvey;
  final VoidCallback onSkip;
  final VoidCallback onNewSession;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 520),
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'ご利用ありがとうございました',
                key: const Key('session-completed'),
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const SizedBox(height: 20),
              const Text('今後の改善のため、1〜2分ほどのアンケートにご協力ください。'),
              const SizedBox(height: 8),
              const Text('回答は開発・検証目的でのみ使用します。'),
              const SizedBox(height: 20),
              if (!choiceCompleted) ...[
                FilledButton(
                  key: const Key('open-survey'),
                  onPressed: isOpeningSurvey ? null : onOpenSurvey,
                  style: _primaryFilledButtonStyle,
                  child: Text(isOpeningSurvey ? '開いています…' : 'アンケートに回答する'),
                ),
                const SizedBox(height: 8),
                OutlinedButton(
                  key: const Key('skip-survey'),
                  onPressed: isOpeningSurvey ? null : onSkip,
                  child: const Text('今回はスキップ'),
                ),
              ],
              if (errorMessage != null) ...[
                const SizedBox(height: 12),
                Text(
                  errorMessage!,
                  key: const Key('survey-error'),
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ],
              if (choiceCompleted) ...[
                const SizedBox(height: 12),
                FilledButton(
                  key: const Key('new-session'),
                  onPressed: onNewSession,
                  style: _primaryFilledButtonStyle,
                  child: const Text('新しいセッションを開始'),
                ),
              ],
            ],
          ),
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
    final profileSummary = response.fairyProfileSummary;
    final otherCandidates = response.topCandidates.skip(1).take(2).toList();
    return Card(
      key: const Key('match-result'),
      color: _matchResultCardColor,
      margin: const EdgeInsets.only(top: 12),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _ResultSection(
              key: const Key('analysis-result-section'),
              title: 'あなたの分析結果',
              backgroundColor: _analysisSectionColor,
              children: [
                _ResultField(
                  label: '性格傾向',
                  value: response.analysis.personality,
                ),
                _ResultField(label: '価値観', value: response.analysis.values),
                _ResultField(
                  label: '隠れた欲求',
                  value: response.analysis.hiddenNeeds,
                ),
                _ResultField(
                  label: '会話スタイル',
                  value: response.analysis.communicationStyle,
                ),
                _ResultField(
                  label: '理想の相手像',
                  value: response.analysis.idealPartnerType,
                ),
                _ResultField(
                  label: '一言要約',
                  value: response.analysis.summary,
                  emphasized: true,
                ),
              ],
            ),
            _ResultSection(
              key: const Key('matching-result-section'),
              title: 'マッチング結果',
              backgroundColor: _matchSectionColor,
              children: [
                _CandidateSummary(candidate: candidate),
                const Divider(height: 28),
                _ResultField(label: '相性スコア', value: '${result.matchScore}点'),
                _ResultField(label: '相性タイプ', value: result.matchLabel),
                _ResultField(label: '相性ポイント', value: result.matchReason),
              ],
            ),
            _ResultSection(
              key: const Key('warning-result-section'),
              title: '注意点',
              backgroundColor: _warningSectionColor,
              children: [_ResultText(value: result.possibleConcern)],
            ),
            _ResultSection(
              key: const Key('message-result-section'),
              title: 'おすすめの最初のメッセージ',
              backgroundColor: _messageSectionColor,
              children: [
                _MessageExample(value: result.recommendedFirstMessage),
              ],
            ),
            if (otherCandidates.isNotEmpty) ...[
              _ResultSection(
                key: const Key('other-candidates-result-section'),
                title: '他にも相性が近かった候補者',
                backgroundColor: _otherCandidatesSectionColor,
                children: [
                  for (var index = 0; index < otherCandidates.length; index++)
                    _OtherCandidate(
                      rank: index + 2,
                      candidate: otherCandidates[index].candidate,
                    ),
                ],
              ),
            ],
            if (support != null) ...[
              _ResultSection(
                key: const Key('support-result-section'),
                title: 'マッチ後支援',
                backgroundColor: _supportSectionColor,
                children: [
                  _ResultField(
                    label: '今日送る一言',
                    value: support.firstMessageToday,
                  ),
                  _ResultField(
                    label: '3日以内に聞く質問',
                    value: support.questionIn3days,
                  ),
                  _ResultField(label: '避けたほうがいい一言', value: support.avoidPhrase),
                  _ResultField(
                    label: '返信が遅いときの対応',
                    value: support.slowReplyAction,
                  ),
                ],
              ),
            ],
            if (profileSummary != null && profileSummary.hasContent)
              _ResultSection(
                key: const Key('fairy-profile-summary-section'),
                title: 'Fairyが覚えたプロフィール',
                backgroundColor: _profileSectionColor,
                children: [
                  _ResultField(
                    label: 'Fairyの理解',
                    value: profileSummary.understanding,
                  ),
                  if (profileSummary.values.any(
                    (value) => value.trim().isNotEmpty,
                  ))
                    _ValueList(values: profileSummary.values),
                  _ResultField(
                    label: '関係スタイル',
                    value: profileSummary.relationshipStyle,
                  ),
                  _ResultField(
                    label: '合いそうな相手',
                    value: profileSummary.goodMatch,
                  ),
                ],
              ),
            _ResultSection(
              key: const Key('profile-update-result-section'),
              title: 'プロフィール更新状態',
              backgroundColor: _profileUpdateSectionColor,
              children: [
                _ResultText(
                  value: response.profileUpdated
                      ? 'Fairyのプロフィールを更新しました'
                      : 'マッチング結果を表示しています。プロフィールは更新されませんでした。',
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _ResultField extends StatelessWidget {
  const _ResultField({
    required this.label,
    required this.value,
    this.emphasized = false,
  });

  final String label;
  final String value;
  final bool emphasized;

  @override
  Widget build(BuildContext context) {
    final displayValue = value.trim();
    if (displayValue.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: Theme.of(
              context,
            ).textTheme.labelLarge?.copyWith(fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 4),
          Text(
            displayValue,
            softWrap: true,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
              height: 1.5,
              fontWeight: emphasized ? FontWeight.w600 : null,
            ),
          ),
        ],
      ),
    );
  }
}

class _ResultSection extends StatelessWidget {
  const _ResultSection({
    super.key,
    required this.title,
    required this.children,
    required this.backgroundColor,
  });

  final String title;
  final List<Widget> children;
  final Color backgroundColor;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: backgroundColor.withValues(alpha: _resultSectionOpacity),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: _resultSectionBorderColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
              color: _resultSectionTitleColor,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 4),
          ...children,
        ],
      ),
    );
  }
}

class _ResultText extends StatelessWidget {
  const _ResultText({required this.value});

  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Text(
        value.trim(),
        softWrap: true,
        style: const TextStyle(height: 1.5),
      ),
    );
  }
}

class _CandidateSummary extends StatelessWidget {
  const _CandidateSummary({required this.candidate});

  final MatchedCandidate candidate;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('1位候補', style: Theme.of(context).textTheme.labelLarge),
          const SizedBox(height: 4),
          Text(
            '${candidate.name}（${candidate.age}歳）',
            style: Theme.of(
              context,
            ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.bold),
          ),
          if (candidate.description.trim().isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              candidate.description.trim(),
              softWrap: true,
              style: const TextStyle(height: 1.5),
            ),
          ],
        ],
      ),
    );
  }
}

class _MessageExample extends StatelessWidget {
  const _MessageExample({required this.value});

  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(top: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Theme.of(
          context,
        ).colorScheme.primaryContainer.withValues(alpha: 0.45),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(
        value.trim(),
        softWrap: true,
        style: const TextStyle(height: 1.5),
      ),
    );
  }
}

class _ValueList extends StatelessWidget {
  const _ValueList({required this.values});

  final List<String> values;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '大切にしていること',
            style: Theme.of(
              context,
            ).textTheme.labelLarge?.copyWith(fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 4),
          for (final value in values)
            if (value.trim().isNotEmpty)
              Text(
                '・${value.trim()}',
                softWrap: true,
                style: const TextStyle(height: 1.5),
              ),
        ],
      ),
    );
  }
}

class _OtherCandidate extends StatelessWidget {
  const _OtherCandidate({required this.rank, required this.candidate});

  final int rank;
  final MatchedCandidate candidate;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('$rank位', style: Theme.of(context).textTheme.labelLarge),
          const SizedBox(height: 4),
          Text(
            '${candidate.name}（${candidate.age}歳）',
            style: const TextStyle(fontWeight: FontWeight.w600),
          ),
          if (candidate.description.trim().isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                candidate.description.trim(),
                softWrap: true,
                style: const TextStyle(height: 1.5),
              ),
            ),
          if (rank == 2) const Divider(height: 24),
        ],
      ),
    );
  }
}

class _ConsentScreen extends StatelessWidget {
  const _ConsentScreen({
    required this.state,
    required this.selectedConsent,
    required this.validationMessage,
    required this.onConsentChanged,
    required this.onContinue,
  });

  final SessionState state;
  final bool? selectedConsent;
  final String? validationMessage;
  final ValueChanged<bool> onConsentChanged;
  final VoidCallback onContinue;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 520),
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text(
                  'このアプリは、AIとチャットすることであなたの性格や価値観を分析し、'
                  'それをもとに一人の人物（架空）とマッチングするアプリです。',
                ),
                const SizedBox(height: 20),
                Text(
                  'ログ保存への同意確認',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 8),
                const Text('このアプリでは、品質改善・動作確認のため、以下の情報を保存します。'),
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 8),
                  child: Text(
                    '・チャット履歴\n'
                    '・分析結果\n'
                    '・マッチング結果\n'
                    '・デバッグ情報\n'
                    '・エラー情報',
                  ),
                ),
                const Text('保存されたログは開発・検証目的でのみ使用します。'),
                const Text('ログは、開発者が管理するGoogle Driveにも保存されます。'),
                const Text('GitHubなどの公開場所には保存しません。'),
                const Text('同意する場合のみ、チャットを開始できます。'),
                const SizedBox(height: 12),
                _ConsentChoiceTile(
                  key: const Key('consent-accept'),
                  label: 'ログ保存に同意します',
                  selected: selectedConsent == true,
                  onTap: state.isLoading ? null : () => onConsentChanged(true),
                ),
                _ConsentChoiceTile(
                  key: const Key('consent-decline'),
                  label: 'ログ保存に同意しません',
                  selected: selectedConsent == false,
                  onTap: state.isLoading ? null : () => onConsentChanged(false),
                ),
                if (validationMessage != null) ...[
                  const SizedBox(height: 8),
                  Text(
                    validationMessage!,
                    key: const Key('consent-validation'),
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ],
                const SizedBox(height: 12),
                if (!state.isUserStorageReady)
                  const Center(child: CircularProgressIndicator())
                else if (state.isLoading)
                  const _LoadingIndicator(
                    key: Key('session-loading'),
                    message: 'Fairyを呼んでいます…',
                  )
                else ...[
                  if (state.storageErrorMessage != null) ...[
                    Text(
                      state.storageErrorMessage!,
                      key: const Key('storage-error'),
                      style: TextStyle(
                        color: Theme.of(context).colorScheme.error,
                      ),
                    ),
                    const SizedBox(height: 12),
                  ],
                  if (state.errorMessage != null &&
                      state.errorAction == SessionErrorAction.sessionStart)
                    _ErrorNotice(
                      key: const Key('session-error'),
                      title: 'Fairyを呼べませんでした',
                      message: state.errorMessage!,
                      retryKey: const Key('session-retry'),
                      onRetry: onContinue,
                    )
                  else
                    FilledButton(
                      key: const Key('start-chat'),
                      onPressed: state.isUserStorageReady ? onContinue : null,
                      style: _primaryFilledButtonStyle,
                      child: const Text('チャットを開始する'),
                    ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ErrorNotice extends StatelessWidget {
  const _ErrorNotice({
    super.key,
    required this.title,
    required this.message,
    required this.retryKey,
    required this.onRetry,
  });

  final String title;
  final String message;
  final Key retryKey;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Card(
      color: colors.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(Icons.error_outline, color: colors.onErrorContainer),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    title,
                    style: TextStyle(
                      color: colors.onErrorContainer,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(message, style: TextStyle(color: colors.onErrorContainer)),
            const SizedBox(height: 8),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                key: retryKey,
                onPressed: onRetry,
                style: OutlinedButton.styleFrom(
                  foregroundColor: colors.onErrorContainer,
                  minimumSize: const Size.fromHeight(44),
                  padding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 10,
                  ),
                  side: BorderSide(
                    color: colors.onErrorContainer.withValues(alpha: 0.6),
                  ),
                ),
                icon: const Icon(Icons.refresh),
                label: const Text('もう一度試す'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LoadingIndicator extends StatelessWidget {
  const _LoadingIndicator({super.key, required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: _loadingBackgroundColor,
          borderRadius: BorderRadius.circular(_chatBubbleRadius),
          border: Border.all(color: _resultSectionBorderColor),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(
              width: 20,
              height: 20,
              child: CircularProgressIndicator(strokeWidth: 2.5),
            ),
            const SizedBox(width: 10),
            Flexible(
              child: Text(
                message,
                style: const TextStyle(color: _fairyBubbleTextColor),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ConsentChoiceTile extends StatelessWidget {
  const _ConsentChoiceTile({
    super.key,
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: selected ? Theme.of(context).colorScheme.primaryContainer : null,
      child: ListTile(
        onTap: onTap,
        leading: Icon(
          selected ? Icons.radio_button_checked : Icons.radio_button_unchecked,
        ),
        title: Text(label),
      ),
    );
  }
}

class _ConsentDeclinedScreen extends StatelessWidget {
  const _ConsentDeclinedScreen({required this.onBack});

  final VoidCallback onBack;

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
              Text(
                'ログ保存に同意されなかったため、チャットを開始できません。',
                key: const Key('consent-declined-message'),
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
              const SizedBox(height: 12),
              const Text(
                'このMVPでは、品質改善・動作確認のためにログ保存が必要です。\n'
                'チャットを利用する場合は、前の画面に戻って「ログ保存に同意します」を選択してください。',
              ),
              const SizedBox(height: 20),
              OutlinedButton(
                key: const Key('back-to-consent'),
                onPressed: onBack,
                child: const Text('戻る'),
              ),
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
    return LayoutBuilder(
      builder: (context, constraints) {
        return Align(
          alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
          child: Column(
            crossAxisAlignment: isUser
                ? CrossAxisAlignment.end
                : CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 4),
                child: Text(
                  isUser ? 'user' : 'Fairy',
                  style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: _fairyBubbleTextColor,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              const SizedBox(height: 3),
              Container(
                key: Key('message-${message.role}'),
                constraints: BoxConstraints(
                  maxWidth: constraints.maxWidth * _chatBubbleMaxWidthRatio,
                ),
                margin: const EdgeInsets.only(bottom: 10),
                padding: const EdgeInsets.symmetric(
                  horizontal: _chatBubbleHorizontalPadding,
                  vertical: _chatBubbleVerticalPadding,
                ),
                decoration: BoxDecoration(
                  color: isUser ? _userBubbleColor : _fairyBubbleColor,
                  borderRadius: BorderRadius.only(
                    topLeft: const Radius.circular(_chatBubbleRadius),
                    topRight: const Radius.circular(_chatBubbleRadius),
                    bottomLeft: Radius.circular(isUser ? _chatBubbleRadius : 6),
                    bottomRight: Radius.circular(
                      isUser ? 6 : _chatBubbleRadius,
                    ),
                  ),
                  border: Border.all(color: _resultSectionBorderColor),
                  boxShadow: const [
                    BoxShadow(
                      color: Color(0x22000000),
                      blurRadius: 5,
                      offset: Offset(0, 2),
                    ),
                  ],
                ),
                child: Text(
                  message.content,
                  softWrap: true,
                  style: TextStyle(
                    color: isUser
                        ? _userBubbleTextColor
                        : _fairyBubbleTextColor,
                    height: 1.45,
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
