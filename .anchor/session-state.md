# Session state (auto-saved — last known reality)

_Updated: 2026-10-25 11:49:01_  ·  branch: `main`

## Uncommitted changes
```
 M .anchor/session-state.md
 M exams/management/commands/seed_cambridge.py
 M exams/tests.py
 M exams/views.py
 M templates/exams/take_exam.html
?? TESTLAR/9/
?? data/cambridge/ielts_full_mock_test_10.json
?? data/cambridge/ielts_full_mock_test_11.json
?? data/cambridge/images/mock_test_10_task1.jpg
?? data/cambridge/images/mock_test_10_varroa_flowchart.jpg
?? data/cambridge/images/mock_test_11_education_house.jpg
?? data/cambridge/images/mock_test_11_task1.jpg
```

Diff stat:
```
 .anchor/session-state.md                    | 44 +++++++-----------------
 exams/management/commands/seed_cambridge.py |  6 ++++
 exams/tests.py                              | 26 ++++++++++++++
 exams/views.py                              | 53 ++++++++++++++++++++++++++---
 templates/exams/take_exam.html              | 42 +++++++++++++++++++++--
 5 files changed, 133 insertions(+), 38 deletions(-)
```

## Recent commits
```
c9c9a55 wes
f3fd899 qdf
496ddf7 rj3iwe
ac11883 feat(exams): let students take exams without a working webcam
2a35e5e feat(exams): relay webcam video via clips and support multi-viewer calls
474e1ac dwqaef
eba6355 w13rwff
a2f0ec8 feat(exams): require webcam during exams with live staff view
```

## Resume
Read `memory/HANDOFF.md` for intent/next-step, then reconcile against the diff above. If HANDOFF.md is older than this checkpoint, trust the diff.
