import 'package:audioplayers/audioplayers.dart';

/// Short UI sounds (assets/sfx): correct, wrong, lesson complete.
class Sfx {
  Sfx._();

  static bool enabled = true;
  static final _players = <String, AudioPlayer>{};

  /// Don't take audio focus, so a sound never cuts off text-to-speech.
  static Future<void> init() async {
    try {
      await AudioPlayer.global.setAudioContext(AudioContextConfig(focus: AudioContextConfigFocus.mixWithOthers).build());
    } catch (_) {}
  }

  static Future<void> play(String name) async {
    if (!enabled) return;
    try {
      final p = _players[name] ??= AudioPlayer()..setReleaseMode(ReleaseMode.stop);
      await p.stop();
      await p.play(AssetSource('sfx/$name.wav'), volume: 0.6, mode: PlayerMode.lowLatency);
    } catch (_) {
      // A missing sound must never break a lesson.
    }
  }

  static void ok() => play('ok');
  static void bad() => play('bad');
  static void win() => play('win');
}
