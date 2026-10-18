import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api.dart';
import 'device.dart';
import 'reminders.dart';

/// Signed-in user, profile summary and a few local preferences.
class AppState extends ChangeNotifier {
  AppState._(this._prefs) : api = Api(_prefs.getString(_tokenKey)) {
    api.onUnauthorized = () {
      if (api.token != null) _clear();
    };
    // Show the last known profile at once; refresh() replaces it.
    if (signedIn) me = readJson(_meCache);
  }

  static const _tokenKey = 'token';
  static const _slowKey = 'slow_speech';
  static const _soundKey = 'haptics';
  static const _sfxKey = 'sfx';
  static const _themeKey = 'theme';
  static const _reminderKey = 'reminder_minutes';
  static const _reminderOnKey = 'reminder_on';
  static const _meCache = 'cache:me';

  static Future<AppState> load() async => AppState._(await SharedPreferences.getInstance());

  final SharedPreferences _prefs;
  final Api api;

  /// Last /me/ response: xp, streak, level, review counts...
  Map<String, dynamic>? me;

  bool get signedIn => api.token != null;
  bool get slowSpeech => _prefs.getBool(_slowKey) ?? false;
  bool get haptics => _prefs.getBool(_soundKey) ?? true;
  bool get sounds => _prefs.getBool(_sfxKey) ?? true;

  ThemeMode get themeMode => switch (_prefs.getString(_themeKey)) {
        'light' => ThemeMode.light,
        'dark' => ThemeMode.dark,
        _ => ThemeMode.system,
      };

  bool get reminderOn => _prefs.getBool(_reminderOnKey) ?? true;

  /// Reminder time as minutes after midnight (default 20:00).
  int get reminderMinutes => _prefs.getInt(_reminderKey) ?? 20 * 60;

  String get levelCode => (me?['level_code'] as String?) ?? 'A1';
  String get displayName {
    final user = (me?['user'] as Map?) ?? {};
    final first = (user['first_name'] as String?) ?? '';
    return first.isNotEmpty ? first : (user['username'] as String? ?? '');
  }

  Future<void> signIn(String username, String password) async {
    final data = await Api(null).post('auth/login/', {'username': username, 'password': password, ...await deviceInfo()});
    await _saveToken(data['token'] as String);
  }

  Future<void> register(Map<String, String> fields) async {
    final data = await Api(null).post('auth/register/', {...fields, ...await deviceInfo()});
    await _saveToken(data['token'] as String);
  }

  Future<void> _saveToken(String token) async {
    api.token = token;
    await _prefs.setString(_tokenKey, token);
    await refresh();
  }

  Future<void> signOut() async {
    try {
      await api.post('auth/logout/');
    } catch (_) {
      // Signing out locally is enough if the server can't be reached.
    }
    _clear();
  }

  /// Erases the account on the server for good, then signs out here.
  Future<void> deleteAccount(String password) async {
    await api.post('auth/delete/', {'password': password});
    _clear();
  }

  void _clear() {
    api.token = null;
    me = null;
    _prefs.remove(_tokenKey);
    for (final k in _prefs.getKeys().where((k) => k.startsWith('cache:') || k.startsWith('lesson-progress-')).toList()) {
      _prefs.remove(k);
    }
    Reminders.cancel();
    notifyListeners();
  }

  Future<void> refresh() async {
    _setMe(await api.get('me/'));
  }

  Future<void> updateProfile({String? level, int? dailyGoal}) async {
    _setMe(await api.post('me/', {'level': ?level, 'daily_goal': ?dailyGoal}));
  }

  void _setMe(Map<String, dynamic> data) {
    me = data;
    writeJson(_meCache, data);
    syncReminders();
    notifyListeners();
  }

  /// Re-plans the week's reminders from the latest profile (skips today once the goal is met).
  void syncReminders() {
    if (!reminderOn || me == null) return;
    final goal = (me!['daily_goal'] as int?) ?? 30;
    Reminders.schedule(
      minutes: reminderMinutes,
      doneToday: ((me!['xp_today'] as int?) ?? 0) >= goal,
      streak: (me!['streak'] as int?) ?? 0,
    );
  }

  Future<void> setReminder({bool? on, int? minutes}) async {
    if (on != null) await _prefs.setBool(_reminderOnKey, on);
    if (minutes != null) await _prefs.setInt(_reminderKey, minutes);
    if (reminderOn) {
      await Reminders.requestPermission();
      syncReminders();
    } else {
      await Reminders.cancel();
    }
    notifyListeners();
  }

  /// First time on the home screen: ask once for notification permission.
  Future<void> askRemindersOnce() async {
    if (_prefs.getBool('notif_asked') ?? false) return;
    await _prefs.setBool('notif_asked', true);
    if (reminderOn) {
      await Reminders.requestPermission();
      syncReminders();
    }
  }

  void setThemeMode(ThemeMode mode) {
    _prefs.setString(_themeKey, mode.name);
    notifyListeners();
  }

  void setSlowSpeech(bool v) {
    _prefs.setBool(_slowKey, v);
    notifyListeners();
  }

  void setHaptics(bool v) {
    _prefs.setBool(_soundKey, v);
    notifyListeners();
  }

  void setSounds(bool v) {
    _prefs.setBool(_sfxKey, v);
    notifyListeners();
  }

  /// Small local JSON store (e.g. a half-finished lesson to resume).
  Map<String, dynamic>? readJson(String key) {
    final raw = _prefs.getString(key);
    if (raw == null) return null;
    try {
      return jsonDecode(raw) as Map<String, dynamic>;
    } catch (_) {
      return null;
    }
  }

  Future<void> writeJson(String key, Map<String, dynamic>? value) =>
      value == null ? _prefs.remove(key) : _prefs.setString(key, jsonEncode(value));
}

/// Gives every screen access to [AppState] and rebuilds dependents on change.
class AppScope extends InheritedNotifier<AppState> {
  const AppScope({super.key, required AppState state, required super.child}) : super(notifier: state);

  static AppState of(BuildContext context) => context.dependOnInheritedWidgetOfExactType<AppScope>()!.notifier!;

  /// Access without subscribing to rebuilds (for callbacks).
  static AppState read(BuildContext context) => context.getInheritedWidgetOfExactType<AppScope>()!.notifier!;
}
