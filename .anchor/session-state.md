# Session state (auto-saved — last known reality)

_Updated: 2026-11-02 12:58:43_  ·  branch: `main`

## Uncommitted changes
```
 M .anchor/session-state.md
 M core/utils.py
 M exams/analysis.py
 M exams/views.py
 M learn/api.py
 M panel/tests.py
 M payments/views.py
 M tgbot/admin_bot.py
 M tgbot/models.py
 M tgbot/services.py
 M tgbot/tests.py
 M users/views.py
?? tgbot/migrations/0004_telegramaccount_alerts_off.py
```

Diff stat:
```
 .anchor/session-state.md | 37 +++++++++++++------------------------
 core/utils.py            | 37 +++++++++++++++++++++++++++++++++----
 exams/analysis.py        |  8 +++-----
 exams/views.py           |  5 +++--
 learn/api.py             |  6 ++----
 panel/tests.py           |  4 ++--
 payments/views.py        |  5 +++--
 tgbot/admin_bot.py       | 18 +++++++++++++++---
 tgbot/models.py          |  1 +
 tgbot/services.py        | 16 ++++++++--------
 tgbot/tests.py           | 32 ++++++++++++++++++++++++++++++++
 users/views.py           | 13 +++++--------
 12 files changed, 120 insertions(+), 62 deletions(-)
```

## Recent commits
```
2c50062 feat(panel): redesign result grading page with sticky nav and tools
0937d93 feat(panel): add per-question answer review to result grading
3d5d7fa feat(tgbot): add bot-only admins managed by superadmin
31991dd feat(tgbot): add admin panel, support chat, result PDFs and band calculator
f3b5766 feat(tgbot): add Telegram bot for exam-day booking and results
678a636 11
26db86b feat(users): add Telegram-style letter avatars with per-user colors
655fc3f feat(panel): add one-click toggle for exam password on passwords page
```

## Resume
Read `memory/HANDOFF.md` for intent/next-step, then reconcile against the diff above. If HANDOFF.md is older than this checkpoint, trust the diff.
