# Session state (auto-saved — last known reality)

_Updated: 2026-10-18 09:43:15_  ·  branch: `main`

## Uncommitted changes
```
 M .anchor/session-state.md
 M core/models.py
 M exams/tests.py
 M exams/urls.py
 M exams/views.py
 M panel/urls.py
 M panel/views.py
 M templates/base.html
 M templates/exams/take_exam.html
 M templates/panel/attempt_detail.html
 M templates/panel/attempts_live.html
 M templates/panel/settings.html
 M templates/privacy.html
?? core/migrations/0004_sitesettings_camera_proctoring.py
?? exams/camera.py
?? templates/partials/camera_permission.html
```

Diff stat:
```
 .anchor/session-state.md            |  38 +++++------
 core/models.py                      |   3 +
 exams/tests.py                      |  49 +++++++++++++++
 exams/urls.py                       |   3 +-
 exams/views.py                      |  16 +++++
 panel/urls.py                       |   1 +
 panel/views.py                      |  18 ++++++
 templates/base.html                 |   1 +
 templates/exams/take_exam.html      | 121 ++++++++++++++++++++++++++++++++++++
 templates/panel/attempt_detail.html |  37 +++++++++++
 templates/panel/attempts_live.html  |  44 +++++++++++++
 templates/panel/settings.html       |   4 ++
 templates/privacy.html              |   7 ++-
 13 files changed, 315 insertions(+), 27 deletions(-)
```

## Recent commits
```
f3c110d feat(exams): ask admins for the exam password too
dad9440 qdwa
450c7a7 feat(exams): require hourly test password to start an exam
0f56e97 3wd4trtr
f1d5ba5 wqegrdh
bd7a1a2 1235465
93ecb5f 3b8begfus
4aae2e5 1234567
```

## Resume
Read `memory/HANDOFF.md` for intent/next-step, then reconcile against the diff above. If HANDOFF.md is older than this checkpoint, trust the diff.
