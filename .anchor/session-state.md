# Session state (auto-saved — last known reality)

_Updated: 2026-10-13 13:18:43_  ·  branch: `main`

## Uncommitted changes
```
 M .anchor/session-state.md
 M mobile/android/app/build.gradle.kts
 M mobile/android/app/src/main/AndroidManifest.xml
 M mobile/lib/core/app_state.dart
 M mobile/lib/core/speech.dart
 M mobile/lib/main.dart
 M mobile/lib/screens/home_shell.dart
 M mobile/lib/screens/learn_tab.dart
 M mobile/lib/screens/lesson/exercise_steps.dart
 M mobile/lib/screens/lesson/lesson_screen.dart
 M mobile/lib/screens/profile_tab.dart
 M mobile/lib/screens/tutor_tab.dart
 M mobile/pubspec.lock
 M mobile/pubspec.yaml
?? mobile/lib/core/reminders.dart
?? mobile/lib/widgets/confetti.dart
```

Diff stat:
```
 .anchor/session-state.md                        |  36 +-
 mobile/android/app/build.gradle.kts             |   6 +
 mobile/android/app/src/main/AndroidManifest.xml |  11 +
 mobile/lib/core/app_state.dart                  |  73 ++-
 mobile/lib/core/speech.dart                     |   7 +-
 mobile/lib/main.dart                            |  18 +-
 mobile/lib/screens/home_shell.dart              |   4 +-
 mobile/lib/screens/learn_tab.dart               | 127 ++--
 mobile/lib/screens/lesson/exercise_steps.dart   | 793 +++++++++++++++---------
 mobile/lib/screens/lesson/lesson_screen.dart    | 510 +++++++++------
 mobile/lib/screens/profile_tab.dart             |  49 ++
 mobile/lib/screens/tutor_tab.dart               |   4 +-
 mobile/pubspec.lock                             |  56 ++
 mobile/pubspec.yaml                             |   4 +-
 14 files changed, 1127 insertions(+), 571 deletions(-)
```

## Recent commits
```
ce093e3 1234
3b438fe efssg
33b82f2 avve
d33ee7f wdes
1f797f8 afsdsd
279e06d afff
1bc4d39 2r4ered
8d24ef4 12345678
```

## Resume
Read `memory/HANDOFF.md` for intent/next-step, then reconcile against the diff above. If HANDOFF.md is older than this checkpoint, trust the diff.
