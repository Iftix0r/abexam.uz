# Session state (auto-saved — last known reality)

_Updated: 2026-10-13 14:15:46_  ·  branch: `main`

## Uncommitted changes
```
 M .anchor/session-state.md
 M learn/api.py
 M learn/models.py
 M learn/services.py
 M learn/tests.py
 M learn/urls.py
 M learn/views.py
 M mobile/lib/screens/learn_tab.dart
 M mobile/lib/screens/lesson/lesson_screen.dart
 M mobile/lib/screens/profile_tab.dart
 M mobile/pubspec.yaml
 M templates/learn/base.html
 M templates/learn/hub.html
 M templates/learn/lesson.html
?? learn/gamification.py
?? learn/migrations/0008_quests_badges_freezes.py
?? mobile/lib/screens/achievements_screen.dart
?? templates/learn/achievements.html
```

Diff stat:
```
 .anchor/session-state.md                     |  54 +-
 learn/api.py                                 |  19 +
 learn/models.py                              |  21 +-
 learn/services.py                            |  23 +-
 learn/tests.py                               |  51 ++
 learn/urls.py                                |   2 +
 learn/views.py                               |  25 +
 mobile/lib/screens/learn_tab.dart            | 836 +++++++++++++++++----------
 mobile/lib/screens/lesson/lesson_screen.dart |  34 +-
 mobile/lib/screens/profile_tab.dart          |   8 +
 mobile/pubspec.yaml                          |   2 +-
 templates/learn/base.html                    |   1 +
 templates/learn/hub.html                     |  72 +++
 templates/learn/lesson.html                  |   3 +
 14 files changed, 802 insertions(+), 349 deletions(-)
```

## Recent commits
```
93ecb5f 3b8begfus
4aae2e5 1234567
55eb282 32iowwfjoenk
ce093e3 1234
3b438fe efssg
33b82f2 avve
d33ee7f wdes
1f797f8 afsdsd
```

## Resume
Read `memory/HANDOFF.md` for intent/next-step, then reconcile against the diff above. If HANDOFF.md is older than this checkpoint, trust the diff.
