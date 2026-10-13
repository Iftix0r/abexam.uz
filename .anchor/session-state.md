# Session state (auto-saved — last known reality)

_Updated: 2026-10-13 14:36:31_  ·  branch: `main`

## Uncommitted changes
```
 M .anchor/session-state.md
 M learn/ai.py
 M learn/api.py
 M learn/models.py
 M learn/services.py
 M learn/tests.py
 M learn/urls.py
 M learn/views.py
 M mobile/lib/screens/learn_tab.dart
 M mobile/lib/screens/lesson/exercise_steps.dart
 M mobile/lib/screens/lesson/lesson_screen.dart
 M mobile/lib/screens/lesson/step_ctl.dart
 M mobile/pubspec.yaml
 M templates/learn/hub.html
 M templates/learn/lesson.html
?? learn/checkpoints.py
?? learn/migrations/0009_checkpoints.py
```

Diff stat:
```
 .anchor/session-state.md                      |  45 +------
 learn/ai.py                                   |  44 +++++++
 learn/api.py                                  |  72 ++++++++++--
 learn/models.py                               |  27 +++++
 learn/services.py                             |  46 ++++++++
 learn/tests.py                                |  78 +++++++++++++
 learn/urls.py                                 |   3 +
 learn/views.py                                |  74 +++++++++++-
 mobile/lib/screens/learn_tab.dart             | 161 +++++++++++++++++++++++++-
 mobile/lib/screens/lesson/exercise_steps.dart |  11 +-
 mobile/lib/screens/lesson/lesson_screen.dart  | 155 ++++++++++++++++++++++---
 mobile/lib/screens/lesson/step_ctl.dart       |   5 +-
 mobile/pubspec.yaml                           |   2 +-
 templates/learn/hub.html                      |  47 +++++++-
 templates/learn/lesson.html                   |  76 +++++++++---
 15 files changed, 756 insertions(+), 90 deletions(-)
```

## Recent commits
```
bd7a1a2 1235465
93ecb5f 3b8begfus
4aae2e5 1234567
55eb282 32iowwfjoenk
ce093e3 1234
3b438fe efssg
33b82f2 avve
d33ee7f wdes
```

## Resume
Read `memory/HANDOFF.md` for intent/next-step, then reconcile against the diff above. If HANDOFF.md is older than this checkpoint, trust the diff.
