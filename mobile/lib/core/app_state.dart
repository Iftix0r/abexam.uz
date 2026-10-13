import 'dart:convert';

import 'package:flutter/widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api.dart';
import 'device.dart';

/// Signed-in user, profile summary and a few local preferences.
class AppState extends ChangeNotifier {
  AppState._(this._prefs) : api = Api(_prefs.getString(_tokenKey)) {
    api.onUnauthorized = () {
      if (api.token != null) _clear();
    };
  }

  static const _tokenKey = 'token';
  static const _slowKey = 'slow_speech';
  static const _soundKey = 'haptics';
  static const _sfxKey = 'sfx';

  static Future<AppState> load() async => AppState._(await SharedPreferences.getInstance());

  final SharedPreferences _prefs;
  final Api api;

  /// Last /me/ response: xp, streak, level, review counts...
  Map<String, dynamic>? me;

  bool get signedIn => api.token != null;
  bool get slowSpeech => _prefs.getBool(_slowKey) ?? false;
  bool get haptics => _prefs.getBool(_soundKey) ?? true;
  bool get sounds => _prefs.getBool(_sfxKey) ?? true;

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

  void _clear() {
    api.token = null;
    me = null;
    _prefs.remove(_tokenKey);
    notifyListeners();
  }

  Future<void> refresh() async {
    me = await api.get('me/');
    notifyListeners();
  }

  Future<void> updateProfile({String? level, int? dailyGoal}) async {
    me = await api.post('me/', {'level': ?level, 'daily_goal': ?dailyGoal});
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
