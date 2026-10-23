# Session state (auto-saved — last known reality)

_Updated: 2026-10-23 09:54:19_  ·  branch: `main`

## Uncommitted changes
```
 M .anchor/session-state.md
 M core/settings.py
 M learn/api.py
 M learn/tests.py
 M mobile/lib/screens/auth_screen.dart
 M templates/login.html
 M templates/register.html
 M users/forms.py
 M users/tests.py
 M users/views.py
?? users/backends.py
```

Diff stat:
```
 .anchor/session-state.md            | 41 ++++++----------------
 core/settings.py                    |  1 +
 learn/api.py                        |  5 ++-
 learn/tests.py                      |  8 +++--
 mobile/lib/screens/auth_screen.dart | 19 ++++-------
 templates/login.html                | 10 +++---
 templates/register.html             | 68 ++++++++++++++++++++++++++-----------
 users/forms.py                      | 57 +++++++++++++++++++++++--------
 users/tests.py                      | 40 ++++++++++++++++++++++
 users/views.py                      | 23 +++++++++----
 10 files changed, 178 insertions(+), 94 deletions(-)
```

## Recent commits
```
ac11883 feat(exams): let students take exams without a working webcam
2a35e5e feat(exams): relay webcam video via clips and support multi-viewer calls
474e1ac dwqaef
eba6355 w13rwff
a2f0ec8 feat(exams): require webcam during exams with live staff view
f3c110d feat(exams): ask admins for the exam password too
dad9440 qdwa
450c7a7 feat(exams): require hourly test password to start an exam
```

## Resume
Read `memory/HANDOFF.md` for intent/next-step, then reconcile against the diff above. If HANDOFF.md is older than this checkpoint, trust the diff.
