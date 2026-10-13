import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'web_bridge.dart';

/// Server address. Override at build time:
///   flutter run --dart-define=API_BASE=http://10.0.2.2:8000
const String apiBase = String.fromEnvironment('API_BASE', defaultValue: 'https://abexam.uz');

/// Send requests through the hidden WebView (see web_bridge.dart) — needed
/// while the site sits behind Imunify360 on shared hosting. A server without
/// that firewall (VPS, local Django) can use plain HTTP: WEB_BRIDGE=false.
const bool useWebBridge = bool.fromEnvironment('WEB_BRIDGE', defaultValue: true);

/// Recognisable User-Agent for plain-HTTP mode.
const String appUserAgent = 'AbExamEnglish/1.0 (Flutter; mobile app)';

class ApiException implements Exception {
  ApiException(this.message, {this.status = 0});

  final String message;
  final int status;

  bool get unauthorized => status == 401;

  @override
  String toString() => message;
}

/// Thin JSON client for /api/learn/ (see learn/api.py on the server).
class Api {
  Api(this.token);

  String? token;
  void Function()? onUnauthorized;

  static final http.Client _client = http.Client();
  static const _timeout = Duration(seconds: 25);

  Uri _uri(String path, [Map<String, String>? query]) =>
      Uri.parse('$apiBase/api/learn/$path').replace(queryParameters: query);

  Map<String, String> get _headers => {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        if (!useWebBridge) 'User-Agent': appUserAgent,
        if (token != null) 'Authorization': 'Bearer $token',
        'X-Api-Token': ?token,
      };

  Future<Map<String, dynamic>> get(String path, {Map<String, String>? query}) =>
      _send('GET', _uri(path, query), null);

  Future<Map<String, dynamic>> post(String path, [Map<String, dynamic>? body]) =>
      _send('POST', _uri(path), jsonEncode(body ?? {}));

  static bool _blockedByFirewall(String body) =>
      body.contains('Imunify360') || body.contains('One moment, please');

  Future<({int status, String body})> _raw(String method, Uri url, String? body) async {
    if (!useWebBridge) {
      final resp = await (method == 'GET'
              ? _client.get(url, headers: _headers)
              : _client.post(url, headers: _headers, body: body))
          .timeout(_timeout);
      return (status: resp.statusCode, body: utf8.decode(resp.bodyBytes, allowMalformed: true));
    }
    final bridge = WebBridge.instance;
    await bridge.ensureReady(apiBase);
    var r = await bridge.fetch(method: method, url: url, headers: _headers, body: body);
    if (_blockedByFirewall(r.body)) {
      // The check's cookie expired: pass it again once, then retry.
      bridge.reset();
      await bridge.ensureReady(apiBase);
      r = await bridge.fetch(method: method, url: url, headers: _headers, body: body);
    }
    return r;
  }

  Future<Map<String, dynamic>> _send(String method, Uri url, String? payload) async {
    ({int status, String body}) resp;
    try {
      resp = await _raw(method, url, payload);
    } on SocketException {
      throw ApiException("Internet aloqasi yo'q. Ulanishni tekshiring.");
    } on TimeoutException {
      throw ApiException("Server javob bermadi. Internetni tekshirib, qayta urinib ko'ring.");
    } on http.ClientException {
      throw ApiException("Server bilan aloqa uzildi.");
    }
    if (resp.status == 0) throw ApiException("Internet aloqasi yo'q. Ulanishni tekshiring.");
    if (_blockedByFirewall(resp.body)) {
      throw ApiException("Hosting himoyasi so'rovni to'xtatdi. Birozdan keyin qayta urinib ko'ring.", status: resp.status);
    }
    Map<String, dynamic> data;
    try {
      final decoded = jsonDecode(resp.body);
      data = decoded is Map<String, dynamic> ? decoded : {'data': decoded};
    } catch (_) {
      throw ApiException('Serverda xatolik (${resp.status}).', status: resp.status);
    }
    if (resp.status >= 400) {
      if (resp.status == 401) onUnauthorized?.call();
      throw ApiException(data['error']?.toString() ?? 'Xatolik (${resp.status})', status: resp.status);
    }
    return data;
  }
}
