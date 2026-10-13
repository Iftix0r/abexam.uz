import 'dart:async';

import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_recognition_error.dart';
import 'package:speech_to_text/speech_recognition_result.dart';
import 'package:speech_to_text/speech_to_text.dart';

/// Outcome of one listening attempt: what was heard, or why nothing was.
class Heard {
  const Heard(this.alternatives, [this.error]);

  /// Recognised phrases, best first; empty when nothing was understood.
  final List<String> alternatives;

  /// Uzbek explanation when nothing was heard.
  final String? error;

  bool get ok => alternatives.isNotEmpty;
}

/// Device text-to-speech and speech recognition, so listening and speaking
/// exercises work without calling the server.
class Speech {
  Speech._();

  static final Speech instance = Speech._();

  final FlutterTts _tts = FlutterTts();
  final SpeechToText _stt = SpeechToText();
  bool _ttsReady = false;
  bool? _sttAvailable;
  String? _localeId;
  bool slow = false;

  // Handlers of the listening session in progress (the plugin takes its
  // status/error callbacks once, at initialize).
  void Function(String status)? _onStatus;
  void Function(SpeechRecognitionError error)? _onError;

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
    if (_sttAvailable == true) return true;
    _sttAvailable = await _stt.initialize(
      onStatus: (s) => _onStatus?.call(s),
      onError: (e) => _onError?.call(e),
    );
    if (_sttAvailable!) {
      // Prefer an English recognizer the phone actually has.
      try {
        final ids = (await _stt.locales()).map((l) => l.localeId).toList();
        String? pick(String id) => ids.where((x) => x.replaceAll('-', '_').toLowerCase() == id).firstOrNull;
        _localeId = pick('en_us') ?? pick('en_gb') ?? ids.where((x) => x.toLowerCase().startsWith('en')).firstOrNull ?? 'en_US';
      } catch (_) {
        _localeId = 'en_US';
      }
    }
    return _sttAvailable!;
  }

  bool get isListening => _stt.isListening;

  static String _explain(String code) {
    switch (code) {
      case 'error_no_match':
        return "Gap tanilmadi. Mikrofonga yaqinroq, balandroq va aniqroq ayting.";
      case 'error_speech_timeout':
        return "Ovoz eshitilmadi. Mikrofonni bosgach darhol gapiring.";
      case 'error_network':
      case 'error_network_timeout':
      case 'error_server':
        return "Ovozni tanish uchun internet kerak. Ulanishni tekshiring.";
      case 'error_permission':
      case 'error_insufficient_permissions':
        return "Mikrofonga ruxsat berilmagan. Sozlamalar → Ilovalar → AbExam English → Ruxsatlar.";
      case 'error_audio':
      case 'error_audio_error':
        return "Mikrofon band. Boshqa ilovani (qo'ng'iroq, diktofon) yoping.";
      case 'error_busy':
      case 'error_recognizer_busy':
      case 'error_client':
        return "Ovoz tanish xizmati band. Bir soniyadan keyin qayta bosing.";
      case 'error_language_not_supported':
      case 'error_language_unavailable':
        return "Telefonda ingliz tili uchun ovoz tanish o'rnatilmagan (Google ilovasi → Ovoz → Tillar).";
      default:
        return "Ovozni tanib bo'lmadi ($code). Qayta urinib ko'ring.";
    }
  }

  /// Listens once (until the speaker pauses) and reports what was heard.
  Future<Heard> listen() async {
    if (!await canListen) {
      return const Heard([], "Telefonda ovozni tanish xizmati topilmadi (Google ilovasini o'rnating yoki yangilang).");
    }
    await _tts.stop();
    if (_stt.isListening) await _stt.stop();

    final done = Completer<Heard>();
    var lastWords = <String>[];
    void finish(Heard h) {
      if (!done.isCompleted) done.complete(h);
    }

    _onError = (e) {
      // "No match" right after a partial result still means we heard something.
      if (lastWords.isNotEmpty) return finish(Heard(lastWords));
      finish(Heard([], _explain(e.errorMsg)));
    };
    _onStatus = (status) {
      // 'done' comes after the final result has been delivered; give a
      // slow recognizer a moment, then use whatever partial result we have.
      if (status == SpeechToText.doneStatus) {
        Future.delayed(const Duration(milliseconds: 1500), () {
          finish(lastWords.isNotEmpty ? Heard(lastWords) : const Heard([], "Ovoz eshitilmadi. Mikrofonni bosib, aniqroq ayting."));
        });
      }
    };

    try {
      await _stt.listen(
        listenOptions: SpeechListenOptions(
          localeId: _localeId,
          listenFor: const Duration(seconds: 20),
          pauseFor: const Duration(seconds: 3),
          partialResults: true,
          cancelOnError: true,
          listenMode: ListenMode.dictation,
        ),
        onResult: (SpeechRecognitionResult r) {
          final alts = r.alternates.map((a) => a.recognizedWords).where((w) => w.trim().isNotEmpty).toList();
          if (alts.isNotEmpty) lastWords = alts;
          if (r.finalResult) finish(Heard(lastWords, lastWords.isEmpty ? "Ovoz eshitilmadi." : null));
        },
      );
    } catch (e) {
      finish(Heard([], "Mikrofonni ishga tushirib bo'lmadi: $e"));
    }
    // Safety net if the recognizer never reports back.
    Future.delayed(const Duration(seconds: 25), () => finish(Heard(lastWords, lastWords.isEmpty ? "Ovoz eshitilmadi." : null)));
    final heard = await done.future;
    _onStatus = null;
    _onError = null;
    return heard;
  }

  Future<void> stopListening() => _stt.stop();
}
