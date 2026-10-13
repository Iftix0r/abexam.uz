# Session state (auto-saved — last known reality)

_Updated: 2026-10-13 12:34:13_  ·  branch: `main`

## Uncommitted changes
```
 M .anchor/session-state.md
 M learn/api.py
 M learn/models.py
 M mobile/lib/core/app_state.dart
 M mobile/lib/screens/auth_screen.dart
 M mobile/pubspec.lock
 M mobile/pubspec.yaml
 M panel/urls.py
 M panel/views.py
 M templates/panel/base.html
 M templates/panel/user_detail.html
?? learn/migrations/0006_api_token_device.py
?? mobile/lib/core/device.dart
?? panel/tests.py
?? templates/panel/english.html
?? templates/panel/english_devices.html
?? templates/panel/english_learners.html
```

Diff stat:
```
 .anchor/session-state.md            | 119 +--------
 learn/api.py                        |  17 +-
 learn/models.py                     |   6 +-
 mobile/lib/core/app_state.dart      |   5 +-
 mobile/lib/screens/auth_screen.dart | 480 +++++++++++++++++++++++++++++-------
 mobile/pubspec.lock                 |  56 +++++
 mobile/pubspec.yaml                 |   5 +-
 panel/urls.py                       |   5 +
 panel/views.py                      | 184 +++++++++++++-
 templates/panel/base.html           |  14 ++
 templates/panel/user_detail.html    |  45 ++++
 11 files changed, 728 insertions(+), 208 deletions(-)
```

## Recent commits
```
33b82f2 avve
d33ee7f wdes
1f797f8 afsdsd
279e06d afff
1bc4d39 2r4ered
8d24ef4 12345678
f1b865d 12332
622206a asnmxkhsh
```

## Resume
Read `memory/HANDOFF.md` for intent/next-step, then reconcile against the diff above. If HANDOFF.md is older than this checkpoint, trust the diff.
