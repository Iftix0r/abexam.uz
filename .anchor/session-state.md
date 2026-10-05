# Session state (auto-saved — last known reality)

_Updated: 2026-10-05 10:55:26_  ·  branch: `main`

## Uncommitted changes
```
 M core/middleware.py
 M exams/admin.py
 M exams/models.py
 M exams/tests.py
 M exams/views.py
 M panel/urls.py
 M panel/views.py
 M templates/exams/exam_detail.html
 M templates/exams/result_detail.html
 M templates/exams/take_exam.html
 M templates/panel/base.html
 M templates/panel/exam_detail.html
 M templates/panel/results_list.html
 M templates/panel/user_detail.html
 M templates/results_list.html
 M users/views.py
?? .anchor/
?? exams/migrations/0011_userresult_status.py
?? templates/panel/result_grade.html
```

Diff stat:
```
 core/middleware.py                 |   6 +-
 exams/admin.py                     |   4 +-
 exams/models.py                    |  26 ++++++++
 exams/tests.py                     |  96 ++++++++++++++++++++++++++-
 exams/views.py                     |  86 +++++++++++-------------
 panel/urls.py                      |   1 +
 panel/views.py                     | 131 +++++++++++++++++++++++++++++++++----
 templates/exams/exam_detail.html   |  10 ++-
 templates/exams/result_detail.html |  62 ++++++++++++++++--
 templates/exams/take_exam.html     |  18 +++++
 templates/panel/base.html          |   1 +
 templates/panel/exam_detail.html   |   2 +-
 templates/panel/results_list.html  |  18 +++--
 templates/panel/user_detail.html   |   2 +-
 templates/results_list.html        |  18 +++--
 users/views.py                     |  12 ++--
 16 files changed, 409 insertions(+), 84 deletions(-)
```

## Recent commits
```
21d81e4 awf
292438a qa
96b7ae3 qddq
a6913d2 adaqfaf
bd47433 qdf
c2d97ff dafa
885a939 qdq
47f27b4 wdqd
```

## Resume
Read `memory/HANDOFF.md` for intent/next-step, then reconcile against the diff above. If HANDOFF.md is older than this checkpoint, trust the diff.
