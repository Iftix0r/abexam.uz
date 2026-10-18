# Session state (auto-saved — last known reality)

_Updated: 2026-10-18 09:33:10_  ·  branch: `main`

## Uncommitted changes
```
 M .anchor/session-state.md
 M exams/passwords.py
 M exams/testlar.py
 M exams/tests.py
 M exams/views.py
 M panel/views.py
 M templates/panel/exam_passwords.html
 M templates/testlar_list.html
?? templates/testlar_password.html
```

Diff stat:
```
 .anchor/session-state.md            |  46 ++-------------
 exams/passwords.py                  | 115 ++++++++++++++++++++++++++----------
 exams/testlar.py                    |  28 +++++++++
 exams/tests.py                      |  25 +++++++-
 exams/views.py                      |  20 ++-----
 panel/views.py                      |   5 +-
 templates/panel/exam_passwords.html |  15 +++++
 templates/testlar_list.html         |   2 +-
 8 files changed, 166 insertions(+), 90 deletions(-)
```

## Recent commits
```
450c7a7 feat(exams): require hourly test password to start an exam
0f56e97 3wd4trtr
f1d5ba5 wqegrdh
bd7a1a2 1235465
93ecb5f 3b8begfus
4aae2e5 1234567
55eb282 32iowwfjoenk
ce093e3 1234
```

## Resume
Read `memory/HANDOFF.md` for intent/next-step, then reconcile against the diff above. If HANDOFF.md is older than this checkpoint, trust the diff.
