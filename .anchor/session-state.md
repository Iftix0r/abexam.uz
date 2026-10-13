# Session state (auto-saved — last known reality)

_Updated: 2026-10-13 14:00:34_  ·  branch: `main`

## Uncommitted changes
```
 M .anchor/session-state.md
 M learn/admin.py
 M learn/api.py
 M learn/models.py
 M learn/services.py
 M learn/tests.py
 M learn/urls.py
 M learn/views.py
 M mobile/lib/screens/home_shell.dart
 M mobile/lib/screens/lesson/lesson_screen.dart
 M mobile/lib/screens/profile_tab.dart
 M mobile/pubspec.yaml
 M panel/tests.py
 M panel/urls.py
 M panel/views.py
 M templates/learn/base.html
 M templates/learn/hub.html
 M templates/learn/lesson.html
 M templates/panel/base.html
?? learn/migrations/0007_drafts_and_releases.py
?? mobile/lib/core/updates.dart
?? templates/learn/app.html
?? templates/panel/english_app.html
```

Diff stat:
```
 .anchor/session-state.md                     | 63 +++++++++-------------------
 learn/admin.py                               | 13 +++++-
 learn/api.py                                 | 42 ++++++++++++++++---
 learn/models.py                              | 46 ++++++++++++++++++++
 learn/services.py                            | 37 +++++++++++++++-
 learn/tests.py                               | 42 +++++++++++++++++++
 learn/urls.py                                |  3 ++
 learn/views.py                               | 56 +++++++++++++++++++++++--
 mobile/lib/screens/home_shell.dart           |  6 ++-
 mobile/lib/screens/lesson/lesson_screen.dart | 59 ++++++++++++++++++++------
 mobile/lib/screens/profile_tab.dart          | 26 ++++++++++++
 mobile/pubspec.yaml                          |  2 +-
 panel/tests.py                               | 12 ++++++
 panel/urls.py                                |  2 +
 panel/views.py                               | 47 ++++++++++++++++++++-
 templates/learn/base.html                    |  6 +++
 templates/learn/hub.html                     | 31 ++++++++++++++
 templates/learn/lesson.html                  | 23 ++++++++--
 templates/panel/base.html                    |  4 ++
 19 files changed, 448 insertions(+), 72 deletions(-)
```

## Recent commits
```
4aae2e5 1234567
55eb282 32iowwfjoenk
ce093e3 1234
3b438fe efssg
33b82f2 avve
d33ee7f wdes
1f797f8 afsdsd
279e06d afff
```

## Resume
Read `memory/HANDOFF.md` for intent/next-step, then reconcile against the diff above. If HANDOFF.md is older than this checkpoint, trust the diff.
