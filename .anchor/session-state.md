# Session state (auto-saved — last known reality)

_Updated: 2026-10-11 14:53:45_  ·  branch: `main`

## Uncommitted changes
```
 M .anchor/session-state.md
 M exams/migrations/0012_exam_attempt.py
 M exams/models.py
 M exams/tests.py
 M exams/views.py
 M panel/urls.py
 M panel/views.py
 M templates/exams/take_exam.html
 M templates/panel/attempts_live.html
?? templates/panel/attempt_detail.html
```

Diff stat:
```
 .anchor/session-state.md              |  38 +++-----
 exams/migrations/0012_exam_attempt.py |   8 +-
 exams/models.py                       |  15 ++++
 exams/tests.py                        |  65 ++++++++++++++
 exams/views.py                        |  71 +++++++++++----
 panel/urls.py                         |   3 +
 panel/views.py                        | 124 +++++++++++++++++++++++++--
 templates/exams/take_exam.html        | 128 ++++++++++++++++++++++++---
 templates/panel/attempts_live.html    | 157 +++++++++++++++++++++++++---------
 9 files changed, 505 insertions(+), 104 deletions(-)
```

## Recent commits
```
2e1770b b7gybgy
2dddd9d grgdhreht
0159495 q2r32tw
f5eff91 "Choose TWO" juftligida bir xil harf ikki marta ball bermaydi
0685d1d 11111ws
aa14b60 deploy.sh ni bajariladigan qilish (./deploy.sh bilan ishga tushishi uchun)
bf4601c IELTS Full Mock Test 6 va 7 (TESTLAR/7) imtihon sifatida qo'shildi
916f0cf 134543
```

## Resume
Read `memory/HANDOFF.md` for intent/next-step, then reconcile against the diff above. If HANDOFF.md is older than this checkpoint, trust the diff.
