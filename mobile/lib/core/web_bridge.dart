import 'dart:async';
import 'dart:convert';

import 'package:flutter/widgets.dart';
import 'package:webview_flutter/webview_flutter.dart';

/// Sends API requests through a hidden WebView.
///
/// The shared hosting runs Imunify360 bot protection, which refuses plain
/// HTTP clients and makes browsers pass a JavaScript check first. A real
/// browser engine passes that check (exactly like the website does), so the
/// app opens /api/learn/health/ in an invisible WebView once and then runs
/// fetch() from inside it, sharing the cookie the check sets.
class WebBridge {
  WebBridge._();

  static final WebBridge instance = WebBridge._();

  static const _marker = 'abexam-api';
  static const _readyTimeout = Duration(seconds: 45);
  static const _callTimeout = Duration(seconds: 30);

  WebViewController? _controller;
  Completer<void>? _ready;
  Uri? _healthUrl;
  final _pending = <int, Completer<({int status, String body})>>{};
  int _seq = 0;

  WebViewController get controller => _controller ??= WebViewController()
    ..setJavaScriptMode(JavaScriptMode.unrestricted)
    ..addJavaScriptChannel('AbExamBridge', onMessageReceived: _onMessage)
    ..setNavigationDelegate(NavigationDelegate(onPageFinished: (_) => _checkReady()));

  /// Loads the health page and waits until the hosting lets the API answer.
  Future<void> ensureReady(String apiBase) {
    final ready = _ready;
    if (ready != null) return ready.future;
    final completer = _ready = Completer<void>();
    _healthUrl = Uri.parse('$apiBase/api/learn/health/');
    controller.loadRequest(_healthUrl!);
    return completer.future.timeout(_readyTimeout, onTimeout: () {
      _ready = null;
      throw TimeoutException('bridge');
    });
  }

  /// Forget the passed check (e.g. its cookie expired) and pass it again next time.
  void reset() {
    _ready = null;
  }

  Future<void> _checkReady() async {
    final ready = _ready;
    if (ready == null || ready.isCompleted) return;
    try {
      final text = await controller.runJavaScriptReturningResult('document.body ? document.body.innerText : ""');
      if ('$text'.contains(_marker) && !ready.isCompleted) ready.complete();
      // Otherwise it's the "One moment, please..." page: it reloads itself
      // after the check and onPageFinished fires again.
    } catch (_) {}
  }

  void _onMessage(JavaScriptMessage message) {
    try {
      final data = jsonDecode(message.message) as Map<String, dynamic>;
      final c = _pending.remove(data['id']);
      c?.complete((status: (data['status'] as num).toInt(), body: '${data['body']}'));
    } catch (_) {}
  }

  /// Runs fetch() inside the WebView; returns status code and raw body.
  Future<({int status, String body})> fetch({
    required String method,
    required Uri url,
    required Map<String, String> headers,
    String? body,
  }) async {
    final id = ++_seq;
    final c = Completer<({int status, String body})>();
    _pending[id] = c;
    final init = {
      'method': method,
      'headers': headers,
      'credentials': 'same-origin',
      'body': ?body,
    };
    final js = '''
(function () {
  var id = ${jsonEncode(id)};
  fetch(${jsonEncode(url.toString())}, ${jsonEncode(init)})
    .then(function (r) { return r.text().then(function (t) {
      AbExamBridge.postMessage(JSON.stringify({id: id, status: r.status, body: t}));
    }); })
    .catch(function (e) {
      AbExamBridge.postMessage(JSON.stringify({id: id, status: 0, body: String(e)}));
    });
})();''';
    await controller.runJavaScript(js);
    return c.future.timeout(_callTimeout, onTimeout: () {
      _pending.remove(id);
      throw TimeoutException('fetch');
    });
  }
}

/// Keeps the bridge's WebView in the widget tree (1×1 px, hidden under the
/// app) — Android only runs a WebView's JavaScript reliably while attached.
class WebBridgeHost extends StatelessWidget {
  const WebBridgeHost({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Stack(children: [
      Positioned(
        left: 0,
        top: 0,
        width: 1,
        height: 1,
        child: IgnorePointer(child: WebViewWidget(controller: WebBridge.instance.controller)),
      ),
      Positioned.fill(child: child),
    ]);
  }
}
