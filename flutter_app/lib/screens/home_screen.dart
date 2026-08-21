import 'package:flutter/material.dart';

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

  @override
  void initState() {
    super.initState();
    _ownsSessionState = widget.sessionState == null;
    _sessionState = widget.sessionState ?? SessionState();
  }

  @override
  void dispose() {
    if (_ownsSessionState) {
      _sessionState.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('フェアリーズ')),
      body: SafeArea(
        child: AnimatedBuilder(
          animation: _sessionState,
          builder: (context, child) {
            final initialMessage = _sessionState.messages.isEmpty
                ? null
                : _sessionState.messages.first;
            return Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 520),
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      if (_sessionState.isLoading)
                        const Center(child: CircularProgressIndicator())
                      else ...[
                        if (initialMessage != null)
                          Card(
                            child: Padding(
                              padding: const EdgeInsets.all(16),
                              child: Text(initialMessage.content),
                            ),
                          ),
                        if (_sessionState.errorMessage != null) ...[
                          Text(
                            _sessionState.errorMessage!,
                            key: const Key('session-error'),
                            style: TextStyle(
                              color: Theme.of(context).colorScheme.error,
                            ),
                          ),
                          const SizedBox(height: 12),
                        ],
                        FilledButton(
                          onPressed: _sessionState.startSession,
                          child: Text(
                            _sessionState.errorMessage == null
                                ? 'セッションを開始'
                                : '再試行',
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}
