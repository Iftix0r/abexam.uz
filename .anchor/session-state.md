# Session state (auto-saved — last known reality)

_Updated: 2026-10-23 10:07:24_  ·  branch: `main`

## Uncommitted changes
```
 M .anchor/session-state.md
 M exams/camera.py
 M templates/panel/_live_camera_js.html
 M templates/panel/attempt_detail.html
 M templates/panel/attempts_live.html
 M templates/partials/camera_permission.html
 M templates/privacy.html
```

Diff stat:
```
 .anchor/session-state.md                  | 63 ++---------------------
 exams/camera.py                           |  4 +-
 templates/panel/_live_camera_js.html      | 85 +++++++++++++++++++++++++++++++
 templates/panel/attempt_detail.html       | 26 +++++++++-
 templates/panel/attempts_live.html        | 58 ++++++++++++++++++++-
 templates/partials/camera_permission.html |  2 +-
 templates/privacy.html                    |  2 +-
 7 files changed, 176 insertions(+), 64 deletions(-)
```

## Recent commits
```
f3fd899 qdf
496ddf7 rj3iwe
ac11883 feat(exams): let students take exams without a working webcam
2a35e5e feat(exams): relay webcam video via clips and support multi-viewer calls
474e1ac dwqaef
eba6355 w13rwff
a2f0ec8 feat(exams): require webcam during exams with live staff view
f3c110d feat(exams): ask admins for the exam password too
```

## Resume
Read `memory/HANDOFF.md` for intent/next-step, then reconcile against the diff above. If HANDOFF.md is older than this checkpoint, trust the diff.
