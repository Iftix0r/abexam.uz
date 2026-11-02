# Session state (auto-saved — last known reality)

_Updated: 2026-11-02 11:54:07_  ·  branch: `main`

## Uncommitted changes
```
 M .anchor/session-state.md
 M .env.example
 M core/audit.py
 M core/middleware.py
 M core/settings.py
 M core/urls.py
 M exams/views.py
 M panel/urls.py
 M panel/views.py
 M templates/panel/base.html
 M templates/users/profile.html
?? templates/panel/exam_day_detail.html
?? templates/panel/exam_days.html
?? templates/tgbot/
?? tgbot/
```

Diff stat:
```
 .anchor/session-state.md     |  37 +++++-----
 .env.example                 |   4 ++
 core/audit.py                |   2 +
 core/middleware.py           |   2 +-
 core/settings.py             |   7 ++
 core/urls.py                 |   3 +
 exams/views.py               |   3 +
 panel/urls.py                |   8 +++
 panel/views.py               | 157 +++++++++++++++++++++++++++++++++++++++++++
 templates/panel/base.html    |   4 ++
 templates/users/profile.html |   7 ++
 11 files changed, 211 insertions(+), 23 deletions(-)
```

## Recent commits
```
678a636 11
26db86b feat(users): add Telegram-style letter avatars with per-user colors
655fc3f feat(panel): add one-click toggle for exam password on passwords page
ffdc6b8 feat(dashboard): redesign dashboard with score ring and section bars
dcb78b6 ielss
fe39d30 waf
b2fd35d qdwff
f24b14c efwea
```

## Resume
Read `memory/HANDOFF.md` for intent/next-step, then reconcile against the diff above. If HANDOFF.md is older than this checkpoint, trust the diff.
