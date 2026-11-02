# Session state (auto-saved — last known reality)

_Updated: 2026-11-02 13:30:31_  ·  branch: `main`

## Uncommitted changes
```
 M .anchor/session-state.md
 M panel/urls.py
 M panel/views.py
 M templates/panel/base.html
 M templates/panel/user_detail.html
 M templates/panel/users_list.html
 M tgbot/tests.py
?? templates/panel/_tg_pill.html
```

Diff stat:
```
 .anchor/session-state.md         | 30 ++++++---------------
 panel/urls.py                    |  2 ++
 panel/views.py                   | 47 +++++++++++++++++++++++++++++---
 templates/panel/base.html        |  8 ++++++
 templates/panel/user_detail.html | 58 ++++++++++++++++++++++++++++++++++++++++
 templates/panel/users_list.html  | 10 ++++++-
 tgbot/tests.py                   | 30 +++++++++++++++++++++
 7 files changed, 159 insertions(+), 26 deletions(-)
```

## Recent commits
```
21db515 sa
8453ac7 acsc
224c148 refactor(tgbot): always show Telegram status on result pages
a9f6088 feat(tgbot): prompt site users to link Telegram and send results on link
2ca6b3c ss
2c50062 feat(panel): redesign result grading page with sticky nav and tools
0937d93 feat(panel): add per-question answer review to result grading
3d5d7fa feat(tgbot): add bot-only admins managed by superadmin
```

## Resume
Read `memory/HANDOFF.md` for intent/next-step, then reconcile against the diff above. If HANDOFF.md is older than this checkpoint, trust the diff.
