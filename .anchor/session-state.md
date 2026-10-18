# Session state (auto-saved — last known reality)

_Updated: 2026-10-18 09:26:24_  ·  branch: `main`

## Uncommitted changes
```
 M .anchor/session-state.md
 M core/models.py
 M exams/tests.py
 M exams/urls.py
 M exams/views.py
 M panel/urls.py
 M panel/views.py
 M templates/exams/exam_detail.html
 M templates/panel/base.html
 M templates/panel/exam_detail.html
 M templates/panel/settings.html
?? core/migrations/0003_sitesettings_exam_password_required.py
?? exams/passwords.py
?? templates/panel/exam_passwords.html
```

Diff stat:
```
 .anchor/session-state.md         | 57 ++++++++----------------------
 core/models.py                   |  3 ++
 exams/tests.py                   | 75 ++++++++++++++++++++++++++++++++++++++++
 exams/urls.py                    |  3 +-
 exams/views.py                   | 39 +++++++++++++++++++++
 panel/urls.py                    |  1 +
 panel/views.py                   | 21 ++++++++++-
 templates/exams/exam_detail.html | 18 ++++++++++
 templates/panel/base.html        |  4 +++
 templates/panel/exam_detail.html |  7 ++++
 templates/panel/settings.html    |  4 +++
 11 files changed, 187 insertions(+), 45 deletions(-)
```

## Recent commits
```
0f56e97 3wd4trtr
f1d5ba5 wqegrdh
bd7a1a2 1235465
93ecb5f 3b8begfus
4aae2e5 1234567
55eb282 32iowwfjoenk
ce093e3 1234
3b438fe efssg
```

## Resume
Read `memory/HANDOFF.md` for intent/next-step, then reconcile against the diff above. If HANDOFF.md is older than this checkpoint, trust the diff.
