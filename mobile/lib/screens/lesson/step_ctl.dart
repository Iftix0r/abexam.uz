import 'package:flutter/foundation.dart';

import '../../core/api.dart';

/// Result of answering one step.
class Outcome {
  const Outcome({required this.ok, this.typo, this.right, this.graded = true, this.title, this.note, this.given});

  final bool ok;

  /// Accepted spelling when the answer had a small slip.
  final String? typo;

  /// Correct answer to show after a wrong attempt.
  final String? right;

  /// False for steps that don't count toward the score (writing, skipped speaking).
  final bool graded;

  /// Overrides the default feedback title / text.
  final String? title;
  final String? note;

  /// What the learner answered (for "Explain my answer").
  final String? given;
}

/// Link between the lesson player and the widget of the current step.
///
/// An exercise sets [check] and flips [ready] once something is answered;
/// steps that finish on their own (matching, speaking) call [resolve].
class StepCtl extends ChangeNotifier {
  StepCtl({required this.onResolve});

  final void Function(Outcome) onResolve;

  bool ready = false;
  bool answered = false;
  Future<Outcome?> Function()? check;
  VoidCallback? hint;
  String? hintLabel;
  bool skippable = false;

  /// Keyboard "Done": check the answer if it's ready (set by the player).
  VoidCallback? submit;

  bool get isExercise => check != null;

  void setReady(bool v) {
    if (ready == v) return;
    ready = v;
    notifyListeners();
  }

  /// Called from a step's initState, i.e. during build — so it doesn't
  /// notify; the player redraws its buttons after the first frame.
  void configure({Future<Outcome?> Function()? check, VoidCallback? hint, String? hintLabel, bool skippable = false}) {
    this.check = check;
    this.hint = hint;
    this.hintLabel = hintLabel;
    this.skippable = skippable;
  }

  void dropHint() {
    hint = null;
    notifyListeners();
  }

  void resolve(Outcome o) => onResolve(o);
}

/// What a step widget may need besides its own JSON.
class StepEnv {
  const StepEnv({
    required this.api,
    required this.words,
    required this.level,
    required this.slug,
    required this.stepIndex,
    required this.wordPool,
    required this.slowSpeech,
    this.dict = const {},
  });

  final Api api;
  final List<Map<String, dynamic>> words;
  final String level;
  final String slug;
  final int stepIndex;

  /// Words from the lesson used as wrong choices in word banks.
  final List<String> wordPool;
  final bool slowSpeech;

  /// Lower-case English word/phrase → Uzbek, for tap-to-translate.
  final Map<String, String> dict;

  bool get beginner => level == 'A1' || level == 'A2';
}
