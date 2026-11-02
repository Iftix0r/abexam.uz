# Session state (auto-saved — last known reality)

_Updated: 2026-11-02 13:04:15_  ·  branch: `main`

## Uncommitted changes
```
 M .anchor/session-state.md
 M core/settings.py
 M templates/dashboard.html
 M templates/exams/result_detail.html
 M templates/exams/take_exam.html
 M tgbot/handlers.py
 M tgbot/services.py
 M tgbot/tests.py
?? templates/partials/tg_connect.html
?? tgbot/context_processors.py
```

Diff stat:
```
 .anchor/session-state.md           | 49 +++++++-------------------------------
 core/settings.py                   |  1 +
 templates/dashboard.html           |  2 ++
 templates/exams/result_detail.html |  1 +
 templates/exams/take_exam.html     |  1 +
 tgbot/handlers.py                  | 27 ++++++++++++++++++---
 tgbot/services.py                  | 20 +++++++++-------
 tgbot/tests.py                     | 25 +++++++++++++++++++
 8 files changed, 74 insertions(+), 52 deletions(-)
```

## Recent commits
```
2ca6b3c ss
2c50062 feat(panel): redesign result grading page with sticky nav and tools
0937d93 feat(panel): add per-question answer review to result grading
3d5d7fa feat(tgbot): add bot-only admins managed by superadmin
31991dd feat(tgbot): add admin panel, support chat, result PDFs and band calculator
f3b5766 feat(tgbot): add Telegram bot for exam-day booking and results
678a636 11
26db86b feat(users): add Telegram-style letter avatars with per-user colors
```

## Resume
Read `memory/HANDOFF.md` for intent/next-step, then reconcile against the diff above. If HANDOFF.md is older than this checkpoint, trust the diff.
