# Session state (auto-saved — last known reality)

_Updated: 2026-10-11 21:20:10_  ·  branch: `main`

## Uncommitted changes
```
 M .anchor/session-state.md
 M learn/admin.py
 M learn/content.py
 M learn/models.py
 M learn/services.py
 M learn/tests.py
 M learn/urls.py
 M learn/views.py
 M templates/learn/hub.html
 M templates/learn/lesson.html
 M templates/learn/review.html
?? data/learn/B1-03-work-study.json
?? data/learn/stories/
?? learn/migrations/0002_mistakes.py
?? templates/learn/leaderboard.html
?? templates/learn/stories.html
?? templates/learn/story.html
```

Diff stat:
```
 .anchor/session-state.md    |  38 ++++++--------
 learn/admin.py              |   8 ++-
 learn/content.py            |  44 ++++++++++++++++
 learn/models.py             |  19 +++++++
 learn/services.py           | 120 +++++++++++++++++++++++++++++++++++++++++++-
 learn/tests.py              |  80 +++++++++++++++++++++++++++--
 learn/urls.py               |   6 +++
 learn/views.py              | 118 ++++++++++++++++++++++++++++++++++++++++---
 templates/learn/hub.html    |  36 +++++++++++++
 templates/learn/lesson.html |  28 +++++++++--
 templates/learn/review.html |  57 +++++++++++++++++++--
 11 files changed, 512 insertions(+), 42 deletions(-)
```

## Recent commits
```
c07d6d8 wfesgrh
46dbc03 efskfsj i ho
0049de3 wkjteskng
f4c347e cvsb
0535fd4 afsfa
9ee6dab jefwe
01fe7a2 qa
5489e63 q3r
```

## Resume
Read `memory/HANDOFF.md` for intent/next-step, then reconcile against the diff above. If HANDOFF.md is older than this checkpoint, trust the diff.
