# Session state (auto-saved — last known reality)

_Updated: 2026-10-25 14:36:57_  ·  branch: `main`

## Uncommitted changes
```
 M .anchor/session-state.md
 M core/models.py
 M core/utils.py
 M exams/views.py
 M panel/tests.py
 M panel/urls.py
 M panel/views.py
 M payments/views.py
 M templates/panel/attempts_live.html
 M templates/panel/base.html
 M templates/panel/exam_analysis.html
 M templates/panel/question_form.html
 M templates/panel/results_list.html
 M templates/panel/settings.html
 M templates/panel/user_detail.html
 M templates/panel/users_list.html
 M users/models.py
?? core/audit.py
?? core/migrations/0005_sitesettings_telegram_work_alerts_auditlog.py
?? exams/analysis.py
?? templates/panel/audit_log.html
?? templates/panel/group_detail.html
?? templates/panel/groups_list.html
?? templates/panel/user_report.html
?? users/migrations/0006_studygroup.py
```

Diff stat:
```
 .anchor/session-state.md           |  47 +++--
 core/models.py                     |  25 +++
 core/utils.py                      |   8 +
 exams/views.py                     |  13 +-
 panel/tests.py                     | 121 +++++++++++
 panel/urls.py                      |   6 +
 panel/views.py                     | 418 ++++++++++++++++++++++++++++++-------
 payments/views.py                  |   8 +-
 templates/panel/attempts_live.html |  12 +-
 templates/panel/base.html          |  10 +
 templates/panel/exam_analysis.html |  11 +-
 templates/panel/question_form.html |  17 +-
 templates/panel/results_list.html  |  10 +-
 templates/panel/settings.html      |   9 +
 templates/panel/user_detail.html   |  24 +++
 templates/panel/users_list.html    |  26 +++
 users/models.py                    |  17 ++
 17 files changed, 672 insertions(+), 110 deletions(-)
```

## Recent commits
```
f24b14c efwea
58501df hjgh
6871102 fa
7f8fafb qdwadf
0884beb feat(exams): render Listening notes as a boxed form with inline gaps
c9c9a55 wes
f3fd899 qdf
496ddf7 rj3iwe
```

## Resume
Read `memory/HANDOFF.md` for intent/next-step, then reconcile against the diff above. If HANDOFF.md is older than this checkpoint, trust the diff.
