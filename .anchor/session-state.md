# Session state (auto-saved — last known reality)

_Updated: 2026-10-18 08:20:06_  ·  branch: `main`

## Uncommitted changes
```
 M .anchor/session-state.md
 M core/urls.py
 M learn/api.py
 M learn/tests.py
 M mobile/android/app/build.gradle.kts
 M mobile/android/app/src/main/AndroidManifest.xml
 M mobile/lib/core/app_state.dart
 M mobile/lib/core/updates.dart
 M mobile/lib/screens/profile_tab.dart
 M users/tests.py
 M users/views.py
?? templates/privacy.html
?? templates/public_base.html
?? templates/users/account_delete.html
```

Diff stat:
```
 .anchor/session-state.md                        | 60 ++++-------------
 core/urls.py                                    |  5 +-
 learn/api.py                                    | 18 ++++-
 learn/tests.py                                  |  8 +++
 mobile/android/app/build.gradle.kts             | 26 +++++++-
 mobile/android/app/src/main/AndroidManifest.xml |  3 -
 mobile/lib/core/app_state.dart                  |  6 ++
 mobile/lib/core/updates.dart                    |  8 +++
 mobile/lib/screens/profile_tab.dart             | 87 ++++++++++++++++++++++++-
 users/tests.py                                  | 34 ++++++++++
 users/views.py                                  | 30 +++++++++
 11 files changed, 228 insertions(+), 57 deletions(-)
```

## Recent commits
```
f1d5ba5 wqegrdh
bd7a1a2 1235465
93ecb5f 3b8begfus
4aae2e5 1234567
55eb282 32iowwfjoenk
ce093e3 1234
3b438fe efssg
33b82f2 avve
```

## Resume
Read `memory/HANDOFF.md` for intent/next-step, then reconcile against the diff above. If HANDOFF.md is older than this checkpoint, trust the diff.
