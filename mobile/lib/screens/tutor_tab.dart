import 'package:flutter/material.dart';

import '../core/app_state.dart';
import '../core/speech.dart';
import '../core/theme.dart';
import '../widgets/common.dart';

class TutorTab extends StatelessWidget {
  const TutorTab({super.key});

  static const _icons = {
    'free': Icons.chat_bubble_rounded,
    'cafe': Icons.local_cafe_rounded,
    'travel': Icons.flight_rounded,
    'interview': Icons.work_rounded,
    'ielts1': Icons.mic_rounded,
    'ielts3': Icons.psychology_rounded,
  };

  @override
  Widget build(BuildContext context) {
    final api = AppScope.of(context).api;
    return SafeArea(
      child: Loader<Map<String, dynamic>>(
        load: () => api.get('tutor/'),
        builder: (context, data, _) {
          final scenarios = (data['scenarios'] as List).cast<Map<String, dynamic>>();
          return ListView(padding: const EdgeInsets.all(16), children: [
            const Text('AI suhbatdosh', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w900)),
            const SizedBox(height: 4),
            Text("Real vaziyatlarda gaplashib mashq qiling. AI xatolaringizni yumshoq tuzatadi va foydali iboralar beradi.",
                style: TextStyle(color: Theme.of(context).colorScheme.outline)),
            const SizedBox(height: 16),
            for (var i = 0; i < scenarios.length; i++)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Card(
                  child: ListTile(
                    contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    leading: Container(
                      width: 48,
                      height: 48,
                      decoration: BoxDecoration(
                        color: Brand.levels.values.elementAt(i % Brand.levels.length).withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: Icon(_icons[scenarios[i]['key']] ?? Icons.chat_rounded,
                          color: Brand.levels.values.elementAt(i % Brand.levels.length)),
                    ),
                    title: Text('${scenarios[i]['title_uz']}', style: const TextStyle(fontWeight: FontWeight.w800)),
                    subtitle: Text('${scenarios[i]['desc_uz']}'),
                    trailing: const Icon(Icons.chevron_right_rounded),
                    onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => TutorChat(scenario: scenarios[i]))),
                  ),
                ),
              ),
          ]);
        },
      ),
    );
  }
}

class _Msg {
  _Msg(this.role, this.text);

  final String role;
  final String text;
  Map<String, dynamic>? correction;
  Map<String, dynamic>? tip;
}

class TutorChat extends StatefulWidget {
  const TutorChat({super.key, required this.scenario});

  final Map<String, dynamic> scenario;

  @override
  State<TutorChat> createState() => _TutorChatState();
}

class _TutorChatState extends State<TutorChat> {
  final _msgs = <_Msg>[];
  final _input = TextEditingController();
  final _scroll = ScrollController();
  bool _sending = false;
  bool _listening = false;
  bool _autoSpeak = true;

  @override
  void initState() {
    super.initState();
    final opener = '${widget.scenario['opener']}';
    _msgs.add(_Msg('assistant', opener));
    Speech.instance.say(opener);
  }

  @override
  void dispose() {
    Speech.instance.stop();
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _toBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(_scroll.position.maxScrollExtent, duration: const Duration(milliseconds: 300), curve: Curves.easeOut);
      }
    });
  }

  Future<void> _send() async {
    final text = _input.text.trim();
    if (text.isEmpty || _sending) return;
    final history = [for (final m in _msgs) {'role': m.role, 'content': m.text}];
    final mine = _Msg('user', text);
    setState(() {
      _msgs.add(mine);
      _sending = true;
      _input.clear();
    });
    _toBottom();
    try {
      final r = await AppScope.read(context).api.post('tutor/send/', {
        'scenario': widget.scenario['key'],
        'message': text,
        'history': history,
      });
      mine.correction = r['correction'] as Map<String, dynamic>?;
      mine.tip = r['tip'] as Map<String, dynamic>?;
      final reply = '${r['reply']}';
      setState(() => _msgs.add(_Msg('assistant', reply)));
      if (_autoSpeak) Speech.instance.say(reply);
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _sending = false);
      _toBottom();
    }
  }

  Future<void> _mic() async {
    if (_listening) {
      await Speech.instance.stopListening();
      return;
    }
    setState(() => _listening = true);
    final heard = await Speech.instance.listen();
    if (!mounted) return;
    setState(() => _listening = false);
    if (heard.ok) {
      _input.text = heard.alternatives.first;
      _input.selection = TextSelection.collapsed(offset: _input.text.length);
    } else {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(heard.error ?? "Ovoz eshitilmadi.")));
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: Text('${widget.scenario['title_uz']}'),
        actions: [
          IconButton(
            tooltip: 'Javobni ovozda o\'qish',
            icon: Icon(_autoSpeak ? Icons.volume_up_rounded : Icons.volume_off_rounded),
            onPressed: () => setState(() => _autoSpeak = !_autoSpeak),
          ),
        ],
      ),
      body: Column(children: [
        Expanded(
          child: ListView.builder(
            controller: _scroll,
            padding: const EdgeInsets.all(14),
            itemCount: _msgs.length + (_sending ? 1 : 0),
            itemBuilder: (context, i) {
              if (i == _msgs.length) {
                return const Align(
                  alignment: Alignment.centerLeft,
                  child: Padding(padding: EdgeInsets.all(12), child: SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.5))),
                );
              }
              final m = _msgs[i];
              final me = m.role == 'user';
              return Column(crossAxisAlignment: me ? CrossAxisAlignment.end : CrossAxisAlignment.start, children: [
                Container(
                  margin: const EdgeInsets.only(bottom: 6),
                  padding: const EdgeInsets.fromLTRB(14, 10, 8, 10),
                  constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width * 0.8),
                  decoration: BoxDecoration(
                    gradient: me ? Brand.heroGradient : null,
                    color: me ? null : Theme.of(context).cardTheme.color,
                    borderRadius: BorderRadius.only(
                      topLeft: const Radius.circular(18),
                      topRight: const Radius.circular(18),
                      bottomLeft: Radius.circular(me ? 18 : 4),
                      bottomRight: Radius.circular(me ? 4 : 18),
                    ),
                  ),
                  child: Row(mainAxisSize: MainAxisSize.min, children: [
                    Flexible(child: Text(m.text, style: TextStyle(fontSize: 16, height: 1.35, color: me ? Colors.white : null))),
                    if (!me)
                      IconButton(
                        visualDensity: VisualDensity.compact,
                        icon: Icon(Icons.volume_up_rounded, size: 18, color: scheme.primary),
                        onPressed: () => Speech.instance.say(m.text),
                      ),
                  ]),
                ),
                if (m.correction != null)
                  _note(Brand.warn, Icons.spellcheck_rounded, '${m.correction!['corrected']}', '${m.correction!['explain_uz'] ?? ''}'),
                if (m.tip != null) _note(Brand.primary, Icons.tips_and_updates_rounded, '${m.tip!['phrase']}', '${m.tip!['uz'] ?? ''}'),
                const SizedBox(height: 6),
              ]);
            },
          ),
        ),
        Container(
          padding: const EdgeInsets.fromLTRB(10, 8, 10, 10),
          decoration: BoxDecoration(color: Theme.of(context).cardTheme.color, border: Border(top: BorderSide(color: scheme.outlineVariant))),
          child: SafeArea(
            top: false,
            child: Row(children: [
              IconButton.filledTonal(
                onPressed: _mic,
                style: IconButton.styleFrom(backgroundColor: _listening ? Brand.bad : null),
                icon: Icon(_listening ? Icons.stop_rounded : Icons.mic_rounded, color: _listening ? Colors.white : null),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: TextField(
                  controller: _input,
                  minLines: 1,
                  maxLines: 4,
                  textCapitalization: TextCapitalization.sentences,
                  onSubmitted: (_) => _send(),
                  decoration: const InputDecoration(hintText: 'Inglizcha yozing yoki gapiring...', isDense: true),
                ),
              ),
              const SizedBox(width: 8),
              IconButton.filled(onPressed: _sending ? null : _send, icon: const Icon(Icons.send_rounded)),
            ]),
          ),
        ),
      ]),
    );
  }

  Widget _note(Color color, IconData icon, String title, String sub) {
    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      padding: const EdgeInsets.all(10),
      constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width * 0.8),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(12)),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(icon, size: 18, color: color),
        const SizedBox(width: 8),
        Flexible(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: TextStyle(fontWeight: FontWeight.w700, color: color)),
            if (sub.isNotEmpty) Text(sub, style: const TextStyle(fontSize: 13)),
          ]),
        ),
      ]),
    );
  }
}
