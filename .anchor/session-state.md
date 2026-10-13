# Session state (auto-saved — last known reality)

_Updated: 2026-10-13 12:15:03_  ·  branch: `main`

## Uncommitted changes
```
 M .anchor/session-state.md
 D mobile/android/.kotlin/sessions/kotlin-compiler-16162234392178940394.salive
 M mobile/android/app/src/main/AndroidManifest.xml
 M mobile/android/app/src/main/res/drawable-v21/launch_background.xml
 M mobile/android/app/src/main/res/drawable/launch_background.xml
 M mobile/android/app/src/main/res/mipmap-hdpi/ic_launcher.png
 M mobile/android/app/src/main/res/mipmap-mdpi/ic_launcher.png
 M mobile/android/app/src/main/res/mipmap-xhdpi/ic_launcher.png
 M mobile/android/app/src/main/res/mipmap-xxhdpi/ic_launcher.png
 M mobile/android/app/src/main/res/mipmap-xxxhdpi/ic_launcher.png
 M mobile/android/app/src/main/res/values-night/styles.xml
 M mobile/android/app/src/main/res/values/styles.xml
 M mobile/ios/Runner.xcodeproj/project.pbxproj
 M mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Contents.json
 M mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-1024x1024@1x.png
 M mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-20x20@1x.png
 M mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-20x20@2x.png
 M mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-20x20@3x.png
 M mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-29x29@1x.png
 M mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-29x29@2x.png
 M mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-29x29@3x.png
 M mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-40x40@1x.png
 M mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-40x40@2x.png
 M mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-40x40@3x.png
 M mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-60x60@2x.png
 M mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-60x60@3x.png
 M mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-76x76@1x.png
 M mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-76x76@2x.png
 M mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-83.5x83.5@2x.png
 M mobile/ios/Runner/Assets.xcassets/LaunchImage.imageset/Contents.json
 M mobile/ios/Runner/Assets.xcassets/LaunchImage.imageset/LaunchImage.png
 M mobile/ios/Runner/Assets.xcassets/LaunchImage.imageset/LaunchImage@2x.png
 M mobile/ios/Runner/Assets.xcassets/LaunchImage.imageset/LaunchImage@3x.png
 M mobile/ios/Runner/Base.lproj/LaunchScreen.storyboard
 M mobile/ios/Runner/Info.plist
 M mobile/lib/core/app_state.dart
 M mobile/lib/main.dart
 M mobile/lib/screens/auth_screen.dart
 M mobile/lib/screens/home_shell.dart
 M mobile/lib/screens/learn_tab.dart
 M mobile/lib/screens/lesson/exercise_steps.dart
 M mobile/lib/screens/lesson/input_steps.dart
 M mobile/lib/screens/lesson/lesson_screen.dart
 M mobile/lib/screens/lesson/step_ctl.dart
 M mobile/lib/screens/profile_tab.dart
 M mobile/lib/widgets/common.dart
 M mobile/pubspec.lock
 M mobile/pubspec.yaml
?? mobile/android/app/src/main/res/drawable-hdpi/
?? mobile/android/app/src/main/res/drawable-mdpi/
?? mobile/android/app/src/main/res/drawable-night-hdpi/
?? mobile/android/app/src/main/res/drawable-night-mdpi/
?? mobile/android/app/src/main/res/drawable-night-xhdpi/
?? mobile/android/app/src/main/res/drawable-night-xxhdpi/
?? mobile/android/app/src/main/res/drawable-night-xxxhdpi/
?? mobile/android/app/src/main/res/drawable-v21/background.png
?? mobile/android/app/src/main/res/drawable-xhdpi/
?? mobile/android/app/src/main/res/drawable-xxhdpi/
?? mobile/android/app/src/main/res/drawable-xxxhdpi/
?? mobile/android/app/src/main/res/drawable/background.png
?? mobile/android/app/src/main/res/mipmap-anydpi-v26/
?? mobile/android/app/src/main/res/values-night-v31/
?? mobile/android/app/src/main/res/values-v31/
?? mobile/android/app/src/main/res/values/colors.xml
?? mobile/assets/
?? mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-50x50@1x.png
?? mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-50x50@2x.png
?? mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-57x57@1x.png
?? mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-57x57@2x.png
?? mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-72x72@1x.png
?? mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-72x72@2x.png
?? mobile/ios/Runner/Assets.xcassets/LaunchBackground.imageset/
?? mobile/lib/core/sfx.dart
```

Diff stat:
```
 .../LaunchImage.imageset/Contents.json             |  10 +-
 .../LaunchImage.imageset/LaunchImage.png           | Bin 68 -> 3630 bytes
 .../LaunchImage.imageset/LaunchImage@2x.png        | Bin 68 -> 7287 bytes
 .../LaunchImage.imageset/LaunchImage@3x.png        | Bin 68 -> 11320 bytes
 .../ios/Runner/Base.lproj/LaunchScreen.storyboard  |  17 +-
 mobile/ios/Runner/Info.plist                       | 134 ++++----
 mobile/lib/core/app_state.dart                     |  23 ++
 mobile/lib/main.dart                               |   3 +
 mobile/lib/screens/auth_screen.dart                |   8 +-
 mobile/lib/screens/home_shell.dart                 |  60 ++--
 mobile/lib/screens/learn_tab.dart                  |   2 +-
 mobile/lib/screens/lesson/exercise_steps.dart      |  31 +-
 mobile/lib/screens/lesson/input_steps.dart         | 130 ++++---
 mobile/lib/screens/lesson/lesson_screen.dart       | 131 ++++++-
 mobile/lib/screens/lesson/step_ctl.dart            |   7 +
 mobile/lib/screens/profile_tab.dart                |  11 +
 mobile/lib/widgets/common.dart                     |  43 ++-
 mobile/pubspec.lock                                | 376 +++++++++++++++++++++
 mobile/pubspec.yaml                                |  25 +-
 48 files changed, 948 insertions(+), 325 deletions(-)
```

## Recent commits
```
d33ee7f wdes
1f797f8 afsdsd
279e06d afff
1bc4d39 2r4ered
8d24ef4 12345678
f1b865d 12332
622206a asnmxkhsh
1a3ea21 sfgdhes
```

## Resume
Read `memory/HANDOFF.md` for intent/next-step, then reconcile against the diff above. If HANDOFF.md is older than this checkpoint, trust the diff.
