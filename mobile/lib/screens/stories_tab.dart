import 'package:flutter/material.dart';

import '../core/app_state.dart';
import '../core/speech.dart';
import '../core/theme.dart';
import '../widgets/common.dart';

class StoriesTab extends StatefulWidget {
  const StoriesTab({super.key});

  @override
  State<StoriesTab> createState() => _StoriesTabState();
}

class _StoriesTabState extends State<StoriesTab> {
  String? _level;
  Key _key = UniqueKey();

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    return SafeArea(
      child: Loader<Map<String, dynamic>>(
        key: _key,
        load: () => state.api.get('stories/'),
        builder: (context, data, reload) {
          final stories = (data['stories'] as List).cast<Map<String, dynamic>>();
          final levels = {for (final s in stories) '${s['level']}'}.toList();
          _level ??= levels.contains(state.levelCode) ? state.levelCode : (levels.isEmpty ? null : levels.first);
          final shown = stories.where((s) => s['level'] == _level).toList();
          return RefreshIndicator(
            onRefresh: reload,
            child: ListView(padding: const EdgeInsets.all(16), children: [
              const Text('Hikoyalar', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w900)),
              const SizedBox(height: 4),
              Text("Darajangizga mos qisqa hikoyalar: tinglang, o'qing va savollarga javob bering.",
                  style: TextStyle(color: Theme.of(context).colorScheme.outline)),
              const SizedBox(height: 14),
              Wrap(spacing: 8, children: [
                for (final l in levels)
                  ChoiceChip(
                    label: Text(l),
                    selected: l == _level,
                    selectedColor: Brand.level(l).withValues(alpha: 0.2),
                    onSelected: (_) => setState(() => _level = l),
                  ),
              ]),
              const SizedBox(height: 14),
              for (final s in shown)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Card(
                    child: InkWell(
                      borderRadius: BorderRadius.circular(16),
                      onTap: () async {
                        await Navigator.of(context).push(MaterialPageRoute(builder: (_) => StoryScreen(slug: '${s['slug']}')));
                        setState(() => _key = UniqueKey());
                      },
                      child: Padding(
                        padding: const EdgeInsets.all(14),
                        child: Row(children: [
                          Container(
                            width: 62,
                            height: 62,
                            alignment: Alignment.center,
                            decoration: BoxDecoration(
                              color: Brand.level('${s['level']}').withValues(alpha: 0.14),
                              borderRadius: BorderRadius.circular(18),
                            ),
                            child: Text('${s['emoji']}', style: const TextStyle(fontSize: 32)),
                          ),
                          const SizedBox(width: 14),
                          Expanded(
                            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                              Text('${s['title']}', style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800)),
                              Text('${s['title_uz']} · ${s['minutes']} daq', style: TextStyle(color: Theme.of(context).colorScheme.outline)),
                            ]),
                          ),
                          if (s['score'] != null)
                            Pill(label: '${s['score']}%', icon: Icons.check_rounded, color: Brand.ok)
                          else
                            const Icon(Icons.chevron_right_rounded),
                        ]),
                      ),
                    ),
                  ),
                ),
            ]),
          );
        },
      ),
    );
  }
}

class StoryScreen extends StatelessWidget {
  const StoryScreen({super.key, required this.slug});

  final String slug;

  @override
  Widget build(BuildContext context) {
    final api = AppScope.read(context).api;
    return Scaffold(
      appBar: AppBar(),
      body: Loader<Map<String, dynamic>>(
        load: () => api.get('stories/$slug/'),
        builder: (context, story, _) => _StoryReader(story: story),
      ),
    );
  }
}

class _StoryReader extends StatefulWidget {
  const _StoryReader({required this.story});

  final Map<String, dynamic> story;

  @override
  State<_StoryReader> createState() => _StoryReaderState();
}

class _StoryReaderState extends State<_StoryReader> {
  final _showUz = <int>{};
  int _playing = -1;
  int _run = 0;
  bool _quiz = false;
  int _q = 0;
  int? _sel;
  bool _revealed = false;
  int _right = 0;
  Map<String, dynamic>? _result;

  List<Map<String, dynamic>> get _paras => (widget.story['paragraphs'] as List).cast<Map<String, dynamic>>();
  List<Map<String, dynamic>> get _questions => (widget.story['questions'] as List).cast<Map<String, dynamic>>();

  @override
  void dispose() {
    _run++;
    Speech.instance.stop();
    super.dispose();
  }

  Future<void> _playAll() async {
    final my = ++_run;
    for (var i = 0; i < _paras.length; i++) {
      if (!mounted || my != _run) return;
      setState(() => _playing = i);
      await Speech.instance.say('${_paras[i]['en']}', rate: 0.95);
    }
    if (mounted && my == _run) setState(() => _playing = -1);
  }

  Future<void> _finish() async {
    final score = _questions.isEmpty ? 100 : (_right * 100 / _questions.length).round();
    try {
      final r = await AppScope.read(context).api.post('stories/${widget.story['slug']}/complete/', {'score': score});
      if (mounted) setState(() => _result = {...r, 'score': score});
      if (mounted) AppScope.read(context).refresh().catchError((_) {});
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) => _quiz ? _quizView() : _readView();

  Widget _readView() {
    final scheme = Theme.of(context).colorScheme;
    final glossary = ((widget.story['glossary'] as Map?) ?? {});
    return ListView(padding: const EdgeInsets.fromLTRB(18, 0, 18, 32), children: [
      Text('${widget.story['emoji']}', style: const TextStyle(fontSize: 52)),
      Text('${widget.story['title']}', style: const TextStyle(fontSize: 28, fontWeight: FontWeight.w900)),
      Text('${widget.story['title_uz']}', style: TextStyle(color: scheme.outline, fontSize: 16)),
      const SizedBox(height: 14),
      FilledButton.tonalIcon(
        onPressed: _playing >= 0
            ? () {
                _run++;
                Speech.instance.stop();
                setState(() => _playing = -1);
              }
            : _playAll,
        icon: Icon(_playing >= 0 ? Icons.stop_rounded : Icons.play_arrow_rounded),
        label: Text(_playing >= 0 ? "To'xtatish" : 'Butun hikoyani tinglash'),
      ),
      const SizedBox(height: 16),
      for (var i = 0; i < _paras.length; i++)
        GestureDetector(
          onTap: () => setState(() => _showUz.contains(i) ? _showUz.remove(i) : _showUz.add(i)),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            margin: const EdgeInsets.only(bottom: 12),
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: _playing == i ? Brand.warnSoft : Theme.of(context).cardTheme.color,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: _playing == i ? Brand.warn : scheme.outlineVariant.withValues(alpha: 0.5)),
            ),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${_paras[i]['en']}', style: TextStyle(fontSize: 17, height: 1.6, color: _playing == i ? Colors.black87 : null)),
              if (_showUz.contains(i)) ...[
                const Divider(height: 18),
                Text('${_paras[i]['uz']}', style: TextStyle(color: _playing == i ? Colors.black54 : scheme.outline, height: 1.5)),
              ],
            ]),
          ),
        ),
      Text("Paragrafni bosing — tarjimasi chiqadi.", style: TextStyle(color: scheme.outline, fontSize: 13)),
      if (glossary.isNotEmpty) ...[
        const SectionTitle("Lug'at"),
        Wrap(spacing: 8, runSpacing: 8, children: [
          for (final e in glossary.entries)
            Chip(label: Text('${e.key} — ${e.value}'), visualDensity: VisualDensity.compact),
        ]),
      ],
      const SizedBox(height: 24),
      if (_questions.isNotEmpty)
        FilledButton.icon(
          onPressed: () {
            _run++;
            Speech.instance.stop();
            setState(() => _quiz = true);
          },
          icon: const Icon(Icons.quiz_rounded),
          label: Text('Savollarga javob berish (${_questions.length})'),
        ),
    ]);
  }

  Widget _quizView() {
    final scheme = Theme.of(context).colorScheme;
    if (_result != null || _q >= _questions.length) {
      if (_result == null) return const Center(child: CircularProgressIndicator());
      final score = _result!['score'] as int;
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Text(score >= 75 ? '📚' : '💡', style: const TextStyle(fontSize: 80)),
            const SizedBox(height: 10),
            Text('$score%', style: const TextStyle(fontSize: 40, fontWeight: FontWeight.w900)),
            Text(score >= 75 ? 'Ajoyib tushunish!' : "Hikoyani yana bir bor tinglab o'qing — ikkinchi o'qishda ko'proq tushunasiz.",
                textAlign: TextAlign.center),
            const SizedBox(height: 8),
            if ((_result!['xp'] ?? 0) > 0) Pill(label: '+${_result!['xp']} XP', icon: Icons.bolt_rounded, color: Brand.warn),
            const SizedBox(height: 28),
            FilledButton(onPressed: () => Navigator.pop(context), child: const Text('Tayyor')),
          ]),
        ),
      );
    }
    final q = _questions[_q];
    final options = (q['options'] as List).map((e) => '$e').toList();
    final answer = q['answer'] as int;
    return Padding(
      padding: const EdgeInsets.all(18),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        LinearProgressIndicator(value: _q / _questions.length, minHeight: 8, borderRadius: BorderRadius.circular(8), color: Brand.ok),
        const SizedBox(height: 24),
        Text('${_q + 1}-savol', style: TextStyle(color: scheme.primary, fontWeight: FontWeight.w800)),
        const SizedBox(height: 6),
        Text('${q['q']}', style: const TextStyle(fontSize: 21, fontWeight: FontWeight.w800)),
        const SizedBox(height: 18),
        for (var i = 0; i < options.length; i++)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Material(
              color: _revealed && i == answer
                  ? Brand.okSoft
                  : _revealed && i == _sel
                      ? Brand.badSoft
                      : _sel == i
                          ? scheme.primary.withValues(alpha: 0.1)
                          : Theme.of(context).cardTheme.color,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
                side: BorderSide(
                  width: 2,
                  color: _revealed && i == answer
                      ? Brand.ok
                      : _revealed && i == _sel
                          ? Brand.bad
                          : _sel == i
                              ? scheme.primary
                              : scheme.outlineVariant,
                ),
              ),
              child: InkWell(
                borderRadius: BorderRadius.circular(16),
                onTap: _revealed ? null : () => setState(() => _sel = i),
                child: Padding(
                  padding: const EdgeInsets.all(15),
                  child: Text(options[i], style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: _revealed && (i == answer || i == _sel) ? Colors.black87 : null)),
                ),
              ),
            ),
          ),
        if (_revealed && q['explain_uz'] != null) Text('${q['explain_uz']}', style: TextStyle(color: scheme.outline)),
        const Spacer(),
        FilledButton(
          onPressed: _sel == null
              ? null
              : () {
                  if (!_revealed) {
                    setState(() {
                      _revealed = true;
                      if (_sel == answer) _right++;
                    });
                    return;
                  }
                  setState(() {
                    _q++;
                    _sel = null;
                    _revealed = false;
                  });
                  if (_q >= _questions.length) _finish();
                },
          child: Text(_revealed ? 'Davom etish' : 'Tekshirish'),
        ),
      ]),
    );
  }
}
