import 'dart:async';

import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_recognition_result.dart';
import 'package:speech_to_text/speech_to_text.dart';

/// Device text-to-speech and speech recognition, so listening and speaking
/// exercises work without calling the server.
class Speech {
  Speech._();

  static final Speech instance = Speech._();

  final FlutterTts _tts = FlutterTts();
  final SpeechToText _stt = SpeechToText();
  bool _ttsReady = false;
  bool? _sttAvailable;
  bool slow = false;

  Future<void> _initTts() async {
    if (_ttsReady) return;
    _ttsReady = true;
    await _tts.awaitSpeakCompletion(true);
    final langs = await _tts.getLanguages;
    final list = langs is List ? langs.map((e) => e.toString()).toList() : <String>[];
    await _tts.setLanguage(list.contains('en-GB') ? 'en-GB' : 'en-US');
  }

  /// Speaks [text]; completes when speech ends (or is stopped).
  Future<void> say(String text, {double rate = 1.0}) async {
    await _initTts();
    await _tts.stop();
    // flutter_tts: 0.5 is normal speed on Android/iOS.
    await _tts.setSpeechRate((0.48 * rate * (slow ? 0.7 : 1)).clamp(0.2, 1.0));
    await _tts.speak(text);
  }

  Future<void> stop() => _tts.stop();

  Future<bool> get canListen async {
    _sttAvailable ??= await _stt.initialize(onError: (_) {}, onStatus: (_) {});
    return _sttAvailable!;
  }

  bool get isListening => _stt.isListening;

  /// Listens once and returns the recognised alternatives (best first),
  /// or null if nothing was heard.
  Future<List<String>?> listen() async {
    if (!await canListen) return null;
    await _tts.stop();
    final done = Completer<List<String>?>();
    await _stt.listen(
      listenOptions: SpeechListenOptions(
        localeId: 'en_US',
        listenFor: const Duration(seconds: 15),
        pauseFor: const Duration(seconds: 3),
        partialResults: false,
        cancelOnError: true,
      ),
      onResult: (SpeechRecognitionResult r) {
        if (!r.finalResult || done.isCompleted) return;
        final alts = r.alternates.map((a) => a.recognizedWords).where((w) => w.trim().isNotEmpty).toList();
        done.complete(alts.isEmpty ? null : alts);
      },
    );
    // Recognition can end without a final result (silence, error).
    Timer.periodic(const Duration(milliseconds: 300), (t) {
      if (done.isCompleted) return t.cancel();
      if (!_stt.isListening && t.tick > 3) {
        t.cancel();
        Future.delayed(const Duration(milliseconds: 600), () {
          if (!done.isCompleted) done.complete(null);
        });
      }
    });
    return done.future;
  }

  Future<void> stopListening() => _stt.stop();
}
