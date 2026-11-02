# Session state (auto-saved — last known reality)

_Updated: 2026-11-02 12:50:46_  ·  branch: `main`

## Uncommitted changes
```
 M .anchor/session-state.md
 M panel/views.py
 M templates/panel/result_grade.html
```

Diff stat:
```
 .anchor/session-state.md          |  27 +-
 panel/views.py                    |  14 +
 templates/panel/result_grade.html | 652 ++++++++++++++++++++++++++------------
 3 files changed, 463 insertions(+), 230 deletions(-)
```

## Recent commits
```
0937d93 feat(panel): add per-question answer review to result grading
3d5d7fa feat(tgbot): add bot-only admins managed by superadmin
31991dd feat(tgbot): add admin panel, support chat, result PDFs and band calculator
f3b5766 feat(tgbot): add Telegram bot for exam-day booking and results
678a636 11
26db86b feat(users): add Telegram-style letter avatars with per-user colors
655fc3f feat(panel): add one-click toggle for exam password on passwords page
ffdc6b8 feat(dashboard): redesign dashboard with score ring and section bars
```

## Resume
Read `memory/HANDOFF.md` for intent/next-step, then reconcile against the diff above. If HANDOFF.md is older than this checkpoint, trust the diff.
