# Session state (auto-saved — last known reality)

_Updated: 2026-10-23 10:01:35_  ·  branch: `main`

## Uncommitted changes
```
 M .anchor/session-state.md
 M learn/tests.py
 M mobile/lib/screens/auth_screen.dart
 M panel/views.py
 M templates/panel/attempt_detail.html
 M templates/panel/attempts_live.html
 M templates/panel/base.html
 M templates/panel/dashboard.html
 M templates/panel/english.html
 M templates/panel/english_devices.html
 M templates/panel/english_learners.html
 M templates/panel/exam_detail.html
 M templates/panel/login_logs.html
 M templates/panel/notifications.html
 M templates/panel/result_grade.html
 M templates/panel/results_list.html
 M templates/panel/transactions_list.html
 M templates/panel/user_detail.html
 M templates/panel/users_list.html
 M users/backends.py
 M users/forms.py
 M users/models.py
 M users/tests.py
```

Diff stat:
```
 templates/panel/attempt_detail.html    |  6 ++--
 templates/panel/attempts_live.html     |  4 +--
 templates/panel/base.html              |  4 +--
 templates/panel/dashboard.html         | 10 +++----
 templates/panel/english.html           |  4 +--
 templates/panel/english_devices.html   |  4 +--
 templates/panel/english_learners.html  |  2 +-
 templates/panel/exam_detail.html       |  2 +-
 templates/panel/login_logs.html        |  6 ++--
 templates/panel/notifications.html     |  2 +-
 templates/panel/result_grade.html      |  6 ++--
 templates/panel/results_list.html      |  2 +-
 templates/panel/transactions_list.html |  2 +-
 templates/panel/user_detail.html       | 12 ++++----
 templates/panel/users_list.html        |  7 +++--
 users/backends.py                      | 18 ++++++++++++
 users/forms.py                         |  6 ++--
 users/models.py                        | 11 +++++++
 users/tests.py                         | 25 +++++++++++-----
 23 files changed, 143 insertions(+), 89 deletions(-)
```

## Recent commits
```
496ddf7 rj3iwe
ac11883 feat(exams): let students take exams without a working webcam
2a35e5e feat(exams): relay webcam video via clips and support multi-viewer calls
474e1ac dwqaef
eba6355 w13rwff
a2f0ec8 feat(exams): require webcam during exams with live staff view
f3c110d feat(exams): ask admins for the exam password too
dad9440 qdwa
```

## Resume
Read `memory/HANDOFF.md` for intent/next-step, then reconcile against the diff above. If HANDOFF.md is older than this checkpoint, trust the diff.
