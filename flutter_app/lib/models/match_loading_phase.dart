enum MatchLoadingPhase { analyzing, matching, memorizing }

MatchLoadingPhase? matchLoadingPhaseFromApi(String value) {
  return switch (value) {
    'analyzing' => MatchLoadingPhase.analyzing,
    'matching' => MatchLoadingPhase.matching,
    'memorizing' => MatchLoadingPhase.memorizing,
    _ => null,
  };
}
