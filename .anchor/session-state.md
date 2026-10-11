# Session state (auto-saved — last known reality)

_Updated: 2026-10-11 15:34:28_  ·  branch: `main`

## Uncommitted changes
```
 M .anchor/session-state.md
 M core/models.py
 M exams/tests.py
 M panel/views.py
 M templates/exams/take_exam.html
 M templates/panel/attempts_live.html
 M templates/panel/settings.html
?? core/migrations/0002_sitesettings_proctor_alarm.py
```

Diff stat:
```
 .anchor/session-state.md           |  28 +++-------
 core/models.py                     |   3 ++
 exams/tests.py                     |  20 +++++++
 panel/views.py                     |   1 +
 templates/exams/take_exam.html     | 103 ++++++++++++++++++++++++++++++++---
 templates/panel/attempts_live.html | 107 ++++++++++++++++++++++++++++++++-----
 templates/panel/settings.html      |   9 ++++
 7 files changed, 228 insertions(+), 43 deletions(-)
```

## Recent commits
```
9ee6dab jefwe
01fe7a2 qa
5489e63 q3r
2e1770b b7gybgy
2dddd9d grgdhreht
0159495 q2r32tw
f5eff91 "Choose TWO" juftligida bir xil harf ikki marta ball bermaydi
0685d1d 11111ws
```

## Resume
Read `memory/HANDOFF.md` for intent/next-step, then reconcile against the diff above. If HANDOFF.md is older than this checkpoint, trust the diff.
