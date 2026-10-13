import 'dart:io';

import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:timezone/data/latest.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

/// Daily study reminder.
///
/// Instead of one repeating alarm, the next 7 days are scheduled one by one
/// and re-planned whenever the app refreshes the profile — so a learner who
/// already reached today's goal isn't nagged today.
class Reminders {
  Reminders._();

  static final _plugin = FlutterLocalNotificationsPlugin();
  static bool _ready = false;
  static const _baseId = 100;

  static const _messages = [
    "📚 Bugungi darsingiz kutyapti — 10 daqiqa yetadi.",
    "🧠 So'zlaringizni takrorlash vaqti keldi. Unutmaslik uchun 5 daqiqa!",
    "🎧 Bitta qisqa hikoya tinglang — quloq ingliz tiliga o'rganadi.",
    "🗣 AI bilan 5 daqiqa gaplashing — gapirish ravonlashadi.",
    "🎯 Xatolar ustida ishlash — eng tez o'sish yo'li.",
    "⭐ Har kuni ozgina — bir yilda katta natija.",
    "🚀 IELTS sari yana bir qadam. Bugungi darsni boshlaymizmi?",
  ];

  static Future<void> _init() async {
    if (_ready) return;
    tzdata.initializeTimeZones();
    // Etc/GMT zones have an inverted sign: UTC+5 (Tashkent) is Etc/GMT-5.
    final offset = DateTime.now().timeZoneOffset;
    final hours = offset.inHours;
    final name = hours == 0 || offset.inMinutes % 60 != 0 ? 'UTC' : 'Etc/GMT${hours > 0 ? '-' : '+'}${hours.abs()}';
    tz.setLocalLocation(tz.getLocation(name));
    await _plugin.initialize(
      settings: const InitializationSettings(
        android: AndroidInitializationSettings('@mipmap/ic_launcher'),
        iOS: DarwinInitializationSettings(
          requestAlertPermission: false,
          requestBadgePermission: false,
          requestSoundPermission: false,
        ),
      ),
    );
    _ready = true;
  }

  /// Asks for permission to show notifications (Android 13+, iOS).
  static Future<bool> requestPermission() async {
    await _init();
    if (Platform.isAndroid) {
      final android = _plugin.resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>();
      return await android?.requestNotificationsPermission() ?? false;
    }
    if (Platform.isIOS) {
      final ios = _plugin.resolvePlatformSpecificImplementation<IOSFlutterLocalNotificationsPlugin>();
      return await ios?.requestPermissions(alert: true, badge: true, sound: true) ?? false;
    }
    return false;
  }

  static Future<void> schedule({required int minutes, required bool doneToday, required int streak}) async {
    try {
      await _init();
      await _plugin.cancelAll();
      final now = tz.TZDateTime.now(tz.local);
      const details = NotificationDetails(
        android: AndroidNotificationDetails(
          'daily_reminder',
          'Kunlik eslatma',
          channelDescription: "Har kuni ingliz tili mashg'ulotini eslatadi",
          importance: Importance.high,
          priority: Priority.high,
        ),
        iOS: DarwinNotificationDetails(),
      );
      for (var d = 0; d < 7; d++) {
        final when = tz.TZDateTime(tz.local, now.year, now.month, now.day + d, minutes ~/ 60, minutes % 60);
        if (d == 0 && (doneToday || when.isBefore(now))) continue;
        final body = d == 0 && streak > 0
            ? "🔥 Seriyangiz $streak kun! Uni uzmaslik uchun bugun ham dars qiling."
            : _messages[(now.day + d) % _messages.length];
        await _plugin.zonedSchedule(
          id: _baseId + d,
          scheduledDate: when,
          notificationDetails: details,
          androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
          title: 'AbExam English',
          body: body,
        );
      }
    } catch (_) {
      // A reminder must never break the app.
    }
  }

  static Future<void> cancel() async {
    try {
      await _init();
      await _plugin.cancelAll();
    } catch (_) {}
  }
}
