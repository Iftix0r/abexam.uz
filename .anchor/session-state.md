# Session state (auto-saved — last known reality)

_Updated: 2026-11-02 12:20:02_  ·  branch: `main`

## Uncommitted changes
```
 M .anchor/session-state.md
 M core/audit.py
 M requirements.txt
 M tgbot/api.py
 M tgbot/handlers.py
 M tgbot/management/commands/tg_webhook.py
 M tgbot/models.py
 M tgbot/services.py
 M tgbot/tests.py
?? exams/fonts/
?? exams/pdf.py
?? tgbot/admin_bot.py
?? tgbot/migrations/0002_telegramaccount_is_banned.py
?? tgbot/ui.py
```

Diff stat:
```
 .anchor/session-state.md                |  56 ++----
 core/audit.py                           |   1 +
 requirements.txt                        |   1 +
 tgbot/api.py                            |  21 ++-
 tgbot/handlers.py                       | 319 ++++++++++++++++++--------------
 tgbot/management/commands/tg_webhook.py |   2 +
 tgbot/models.py                         |   2 +
 tgbot/services.py                       |  49 ++++-
 tgbot/tests.py                          | 110 +++++++++++
 9 files changed, 375 insertions(+), 186 deletions(-)
```

## Recent commits
```
f3b5766 feat(tgbot): add Telegram bot for exam-day booking and results
678a636 11
26db86b feat(users): add Telegram-style letter avatars with per-user colors
655fc3f feat(panel): add one-click toggle for exam password on passwords page
ffdc6b8 feat(dashboard): redesign dashboard with score ring and section bars
dcb78b6 ielss
fe39d30 waf
b2fd35d qdwff
```

## Resume
Read `memory/HANDOFF.md` for intent/next-step, then reconcile against the diff above. If HANDOFF.md is older than this checkpoint, trust the diff.
