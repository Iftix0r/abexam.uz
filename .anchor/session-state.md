# Session state (auto-saved — last known reality)

_Updated: 2026-10-05 11:06:12_  ·  branch: `main`

## Uncommitted changes
```
 M .anchor/session-state.md
 M exams/tests.py
 M exams/views.py
 M panel/views.py
 M templates/exams/result_detail.html
 M templates/panel/result_grade.html
 M templates/panel/results_list.html
```

Diff stat:
```
 .anchor/session-state.md           |  27 +---
 exams/tests.py                     |  40 +++++-
 exams/views.py                     |   4 +-
 panel/views.py                     | 183 ++++++++++++++++-------
 templates/exams/result_detail.html |  41 +++++-
 templates/panel/result_grade.html  | 287 ++++++++++++++++++++++++++-----------
 templates/panel/results_list.html  |   4 +-
 7 files changed, 420 insertions(+), 166 deletions(-)
```

## Recent commits
```
175e547 Natija sahifasida javoblar admin uchun ham sukut bo'yicha yashirildi
bfd381a Writingni admin qo'lda baholaydi, natija tekshiruvgacha yashiriladi, javoblar o'quvchidan yashirildi
21d81e4 awf
292438a qa
96b7ae3 qddq
a6913d2 adaqfaf
bd47433 qdf
c2d97ff dafa
```

## Resume
Read `memory/HANDOFF.md` for intent/next-step, then reconcile against the diff above. If HANDOFF.md is older than this checkpoint, trust the diff.
