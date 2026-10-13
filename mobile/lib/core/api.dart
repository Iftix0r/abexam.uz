import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

/// Server address. Override at build time:
///   flutter run --dart-define=API_BASE=http://10.0.2.2:8000
const String apiBase = String.fromEnvironment('API_BASE', defaultValue: 'https://abexam.uz');

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

  final http.Client _client = http.Client();
  static const _timeout = Duration(seconds: 25);

  Uri _uri(String path, [Map<String, String>? query]) =>
      Uri.parse('$apiBase/api/learn/$path').replace(queryParameters: query);

  Map<String, String> get _headers => {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

  Future<Map<String, dynamic>> get(String path, {Map<String, String>? query}) =>
      _send(() => _client.get(_uri(path, query), headers: _headers));

  Future<Map<String, dynamic>> post(String path, [Map<String, dynamic>? body]) =>
      _send(() => _client.post(_uri(path), headers: _headers, body: jsonEncode(body ?? {})));

  Future<Map<String, dynamic>> _send(Future<http.Response> Function() call) async {
    http.Response resp;
    try {
      resp = await call().timeout(_timeout);
    } on SocketException {
      throw ApiException("Internet aloqasi yo'q. Ulanishni tekshiring.");
    } on TimeoutException {
      throw ApiException("Server javob bermadi. Qayta urinib ko'ring.");
    } on http.ClientException {
      throw ApiException("Server bilan aloqa uzildi.");
    }
    Map<String, dynamic> data;
    try {
      final decoded = jsonDecode(utf8.decode(resp.bodyBytes));
      data = decoded is Map<String, dynamic> ? decoded : {'data': decoded};
    } catch (_) {
      throw ApiException('Serverda xatolik (${resp.statusCode}).', status: resp.statusCode);
    }
    if (resp.statusCode >= 400) {
      if (resp.statusCode == 401) onUnauthorized?.call();
      throw ApiException(data['error']?.toString() ?? 'Xatolik (${resp.statusCode})', status: resp.statusCode);
    }
    return data;
  }
}
