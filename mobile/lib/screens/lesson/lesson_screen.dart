import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api.dart';
import '../../core/app_state.dart';
import '../../core/sfx.dart';
import '../../core/speech.dart';
import '../../core/text.dart';
import '../../core/theme.dart';
import '../../widgets/common.dart';
import '../../widgets/confetti.dart';
import 'exercise_steps.dart';
import 'input_steps.dart';
import 'step_ctl.dart';

/// Plays a lesson (or a mixed-practice session) step by step, like the
/// website's lesson player: wrong answers come back at the end, the score
/// counts first attempts, and the result is saved to the server.
class LessonScreen extends StatelessWidget {
  const LessonScreen.lesson(String this.slug, {super.key}) : practice = false;
  const LessonScreen.practice({super.key}) : slug = null, practice = true;

  final String? slug;
  final bool practice;

  @override
  Widget build(BuildContext context) {
    final state = AppScope.read(context);
    final api = state.api;
    return Scaffold(
      body: SafeArea(
        child: Loader<Map<String, dynamic>>(
          load: () async {
            if (practice) return api.get('practice/');
            // Keep opened lessons on the phone, so a weak connection doesn't block re-reading one.
            final key = 'cache:lesson:$slug';
            try {
              final data = await api.get('lessons/$slug/');
              state.writeJson(key, data);
              return data;
            } on ApiException catch (e) {
              final cached = e.status == 0 ? state.readJson(key) : null;
              if (cached == null) rethrow;
              return cached;
            }
          },
          builder: (context, data, _) {
            if ((data['steps'] as List).isEmpty) {
              return _Empty(onClose: () => Navigator.pop(context));
            }
            return _Player(data: data, practice: practice);
          },
        ),
      ),
    );
  }
}

class _Empty extends StatelessWidget {
  const _Empty({required this.onClose});

  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('🎯', style: TextStyle(fontSize: 64)),
            const SizedBox(height: 12),
            const Text('Hali mashq yo\'q', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800)),
            const SizedBox(height: 8),
            const Text(
              "Bir nechta dars o'ting — xato qilgan mashqlaringiz shu yerda qayta beriladi.",
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 24),
            FilledButton(onPressed: onClose, child: const Text('Darslarga qaytish')),
          ],
        ),
      ),
    );
  }
}

const _praise = ["To'g'ri!", 'Barakalla!', "Zo'r!", 'Ajoyib!', 'Aynan shunday!', 'Mukammal!'];

class _Player extends StatefulWidget {
  const _Player({required this.data, required this.practice});

  final Map<String, dynamic> data;
  final bool practice;

  @override
  State<_Player> createState() => _PlayerState();
}

class _PlayerState extends State<_Player> {
  late final List<Map<String, dynamic>> _steps = (widget.data['steps'] as List).cast<Map<String, dynamic>>();
  late final List<Map<String, dynamic>> _words = ((widget.data['words'] as List?) ?? []).cast<Map<String, dynamic>>();
  late final List<int> _queue = List.generate(_steps.length, (i) => i);
  late final List<String> _pool = _buildPool();
  late final Map<String, String> _dict = _buildDict();
  late final List<Map<String, dynamic>> _grammar = _steps.where((s) => s['type'] == 'grammar').toList();
  late StepCtl _ctl;

  int _pos = 0;
  int _combo = 0;
  final _firstTry = <int, bool>{};
  final _retried = <int>{};
  final _mistakes = <int, String>{};
  Outcome? _feedback;
  bool _checking = false;
  Map<String, dynamic>? _result;
  Object? _saveError;
  bool _saving = false;

  String get _level => (widget.data['level'] as String?) ?? AppScope.read(context).levelCode;

  // A half-finished lesson is kept on the phone and offered on the next open.
  String get _saveKey => 'lesson-progress-${widget.data['slug']}';
  String get _sig => '${_steps.length}:${_words.length}';

  @override
  void initState() {
    super.initState();
    _ctl = _newCtl();
    if (!widget.practice) WidgetsBinding.instance.addPostFrameCallback((_) => _offerResume());
  }

  Future<void> _offerResume() async {
    final state = AppScope.read(context);
    final saved = state.readJson(_saveKey);
    if (saved == null) return;
    final age = DateTime.now().millisecondsSinceEpoch - ((saved['at'] as num?) ?? 0);
    final queue = ((saved['queue'] as List?) ?? []).cast<int>();
    final pos = (saved['pos'] as int?) ?? 0;
    if (saved['sig'] != _sig || pos <= 0 || pos >= queue.length || age > const Duration(days: 7).inMilliseconds) {
      state.writeJson(_saveKey, null);
      return;
    }
    final resume = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (c) => AlertDialog(
        title: const Text('Davom ettirasizmi?'),
        content: Text('Bu darsni oldin boshlagan edingiz: ${pos + 1} / ${queue.length}-qadam.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Boshidan')),
          FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Davom etish')),
        ],
      ),
    );
    if (!mounted) return;
    if (resume != true) {
      state.writeJson(_saveKey, null);
      return;
    }
    setState(() {
      _queue
        ..clear()
        ..addAll(queue);
      _pos = pos;
      _firstTry
        ..clear()
        ..addAll({for (final e in ((saved['firstTry'] as Map?) ?? {}).entries) int.parse('${e.key}'): e.value == true});
      _retried
        ..clear()
        ..addAll(((saved['retried'] as List?) ?? []).cast<int>());
      _mistakes
        ..clear()
        ..addAll({for (final e in ((saved['mistakes'] as Map?) ?? {}).entries) int.parse('${e.key}'): '${e.value}'});
      _ctl.removeListener(_redraw);
      _ctl.dispose();
      _ctl = _newCtl();
    });
  }

  void _saveProgress() {
    if (widget.practice) return;
    AppScope.read(context).writeJson(_saveKey, {
      'sig': _sig,
      'queue': _queue,
      'pos': _pos,
      'firstTry': {for (final e in _firstTry.entries) '${e.key}': e.value},
      'retried': _retried.toList(),
      'mistakes': {for (final e in _mistakes.entries) '${e.key}': e.value},
      'at': DateTime.now().millisecondsSinceEpoch,
    });
  }

  Map<String, String> _buildDict() {
    final dict = <String, String>{};
    for (final w in _words) {
      for (var k in '${w['en']}'.split(' / ')) {
        k = k.replaceAll(RegExp(r'[?!.]+$'), '').trim().toLowerCase();
        if (k.isNotEmpty) dict[k] = '${w['uz']}';
      }
    }
    for (final s in _steps) {
      ((s['glossary'] as Map?) ?? {}).forEach((k, v) => dict['$k'.toLowerCase()] = '$v');
    }
    return dict;
  }

  @override
  void dispose() {
    _ctl.dispose();
    Speech.instance.stop();
    super.dispose();
  }

  List<String> _buildPool() {
    final pool = <String>{};
    for (final s in _steps) {
      final a = s['answer'];
      final first = a is List ? (a.isEmpty ? null : a.first) : a;
      if (first is String) pool.addAll(tokensOf(first));
    }
    for (final w in _words) {
      pool.addAll(tokensOf('${w['en']}'.split(' / ').first));
    }
    return pool.toList();
  }

  StepCtl _newCtl() {
    final ctl = StepCtl(onResolve: _resolve)..addListener(_redraw);
    ctl.submit = () {
      if (ctl.ready && !ctl.answered && !_checking) _check();
    };
    // Steps configure the controller while building; show their buttons next frame.
    WidgetsBinding.instance.addPostFrameCallback((_) => _redraw());
    return ctl;
  }

  void _redraw() {
    if (mounted) setState(() {});
  }

  void _haptic(bool ok) {
    if (!AppScope.read(context).haptics) return;
    ok ? HapticFeedback.lightImpact() : HapticFeedback.heavyImpact();
  }

  Future<void> _check() async {
    final check = _ctl.check;
    if (check == null || _ctl.answered) return _next();
    setState(() => _checking = true);
    final o = await check();
    if (!mounted) return;
    setState(() => _checking = false);
    if (o != null) _resolve(o);
  }

  void _resolve(Outcome o) {
    if (_ctl.answered) return;
    _ctl.answered = true;
    final idx = _queue[_pos];
    if (o.graded) {
      _firstTry.putIfAbsent(idx, () => o.ok);
      if (!o.ok) {
        _combo = 0;
        if (_retried.add(idx)) _queue.add(idx);
        _mistakes.putIfAbsent(idx, () => o.right ?? '');
      } else {
        _combo++;
      }
      _haptic(o.ok);
      o.ok ? Sfx.ok() : Sfx.bad();
    }
    setState(() => _feedback = o);
  }

  void _next() {
    Speech.instance.stop();
    FocusScope.of(context).unfocus();
    setState(() {
      _pos++;
      _feedback = null;
      _ctl.removeListener(_redraw);
      _ctl.dispose();
      _ctl = _newCtl();
    });
    if (_pos >= _queue.length) {
      _finish();
    } else {
      _saveProgress();
    }
  }

  int get _score {
    if (_firstTry.isEmpty) return 100;
    return (_firstTry.values.where((v) => v).length * 100 / _firstTry.length).round();
  }

  Future<void> _finish() async {
    setState(() {
      _saving = true;
      _saveError = null;
    });
    final api = AppScope.read(context).api;
    try {
      final Map<String, dynamic> r;
      if (widget.practice) {
        r = await api.post('practice/complete/', {
          'id': widget.data['id'],
          'results': [
            for (final e in _firstTry.entries)
              {'slug': _steps[e.key]['_src']['slug'], 'step': _steps[e.key]['_src']['idx'], 'ok': e.value},
          ],
        });
      } else {
        r = await api.post('lessons/${widget.data['slug']}/complete/', {
          'score': _score,
          'mistakes': [
            for (final e in _firstTry.entries)
              if (!e.value) e.key,
          ],
        });
      }
      if (!mounted) return;
      setState(() => _result = r);
      Sfx.win();
      final state = AppScope.read(context);
      if (!widget.practice) state.writeJson(_saveKey, null);
      state.refresh().catchError((_) {});
    } catch (e) {
      if (mounted) setState(() => _saveError = e);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<bool> _confirmExit() async {
    if (_pos >= _queue.length || _pos == 0) return true;
    final leave = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('Darsni tark etasizmi?'),
        content: Text(widget.practice ? 'Natija saqlanmaydi.' : "Keyingi safar shu joydan davom ettirishingiz mumkin."),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Davom etish')),
          TextButton(
            onPressed: () => Navigator.pop(c, true),
            child: const Text('Chiqish', style: TextStyle(color: Brand.bad)),
          ),
        ],
      ),
    );
    return leave ?? false;
  }

  Widget _stepWidget(int idx) {
    final step = _steps[idx];
    final key = ValueKey('step-$_pos');
    final env = StepEnv(
      api: AppScope.read(context).api,
      words: _words,
      level: _level,
      slug: '${step['_src']?['slug'] ?? widget.data['slug']}',
      stepIndex: (step['_src']?['idx'] as int?) ?? idx,
      wordPool: _pool,
      slowSpeech: Speech.instance.slow,
      dict: _dict,
    );
    switch (step['type']) {
      case 'words':
        return WordsStep(key: key, words: _words);
      case 'dialogue':
        return DialogueStep(key: key, step: step);
      case 'reading':
        return ReadingStep(key: key, step: step);
      case 'grammar':
        return GrammarStep(key: key, step: step);
      case 'choice':
        return ChoiceStep(key: key, step: step, ctl: _ctl, env: env);
      case 'gap':
        return GapStep(key: key, step: step, ctl: _ctl, env: env);
      case 'translate':
        return TypedStep(key: key, step: step, ctl: _ctl, env: env, dictation: false);
      case 'listen':
        return TypedStep(key: key, step: step, ctl: _ctl, env: env, dictation: true);
      case 'order':
        return OrderStep(key: key, step: step, ctl: _ctl);
      case 'match':
        return MatchStep(key: key, step: step, ctl: _ctl);
      case 'speak':
        return SpeakStep(key: key, step: step, ctl: _ctl);
      case 'write':
        return WriteStep(key: key, step: step, ctl: _ctl, env: env);
      default:
        return GrammarStep(key: key, step: step, tip: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final done = _pos >= _queue.length;
    return PopScope(
      canPop: done || _pos == 0,
      onPopInvokedWithResult: (didPop, _) async {
        if (didPop) return;
        final nav = Navigator.of(context);
        if (await _confirmExit()) nav.pop();
      },
      child: done ? _finishView() : _playView(),
    );
  }

  Widget _playView() {
    final idx = _queue[_pos];
    final step = _steps[idx];
    final scheme = Theme.of(context).colorScheme;
    final slow = Speech.instance.slow;
    final wasWrong = step['_src']?['mistake'] == true;
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(4, 6, 12, 6),
          child: Row(
            children: [
              IconButton(
                icon: const Icon(Icons.close_rounded),
                onPressed: () async {
                  final nav = Navigator.of(context);
                  if (await _confirmExit()) nav.pop();
                },
              ),
              Expanded(
                child: TweenAnimationBuilder<double>(
                  tween: Tween(end: _pos / _queue.length),
                  duration: const Duration(milliseconds: 400),
                  curve: Curves.easeOutCubic,
                  builder: (_, v, _) => ClipRRect(
                    borderRadius: BorderRadius.circular(8),
                    child: LinearProgressIndicator(
                      value: v,
                      minHeight: 12,
                      backgroundColor: scheme.surfaceContainerHighest,
                      color: Brand.ok,
                    ),
                  ),
                ),
              ),
              if (_combo >= 3) ...[
                const SizedBox(width: 8),
                Pill(label: '$_combo', icon: Icons.local_fire_department_rounded, color: Brand.flame),
              ],
              if (_grammar.isNotEmpty && step['type'] != 'grammar')
                IconButton(
                  tooltip: 'Dars qoidasi',
                  icon: Icon(Icons.menu_book_rounded, color: scheme.primary),
                  onPressed: _showGrammar,
                ),
              IconButton(
                tooltip: 'Sekin talaffuz',
                icon: Icon(Icons.speed_rounded, color: slow ? scheme.primary : scheme.outline),
                onPressed: () {
                  Speech.instance.slow = !slow;
                  AppScope.read(context).setSlowSpeech(!slow);
                  ScaffoldMessenger.of(context)
                    ..hideCurrentSnackBar()
                    ..showSnackBar(
                      SnackBar(
                        content: Text(!slow ? 'Sekin talaffuz yoqildi 🐢' : 'Odatiy tezlik'),
                        duration: const Duration(seconds: 1),
                      ),
                    );
                },
              ),
            ],
          ),
        ),
        Expanded(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(18, 8, 18, 24),
            child: AnimatedSwitcher(
              duration: const Duration(milliseconds: 280),
              transitionBuilder: (child, a) => FadeTransition(
                opacity: a,
                child: SlideTransition(
                  position: Tween(begin: const Offset(0.06, 0), end: Offset.zero).animate(a),
                  child: child,
                ),
              ),
              child: Column(
                key: ValueKey('wrap-$_pos'),
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (wasWrong)
                    const Align(
                      alignment: Alignment.centerLeft,
                      child: Padding(
                        padding: EdgeInsets.only(bottom: 8),
                        child: Pill(label: 'avval xato qilgansiz', color: Brand.warn),
                      ),
                    ),
                  _stepWidget(idx),
                ],
              ),
            ),
          ),
        ),
        _bottomBar(),
      ],
    );
  }

  void _showGrammar() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.7,
        maxChildSize: 0.95,
        builder: (_, scroll) => ListView(
          controller: scroll,
          padding: const EdgeInsets.fromLTRB(18, 0, 18, 32),
          children: [
            for (final g in _grammar) ...[
              StepTitle('${g['title_uz'] ?? ''}'),
              GrammarCard(step: g),
              const SizedBox(height: 16),
            ],
          ],
        ),
      ),
    );
  }

  Widget _bottomBar() {
    final fb = _feedback;
    final scheme = Theme.of(context).colorScheme;
    if (fb != null) {
      final typo = fb.typo != null;
      final color = !fb.graded
          ? scheme.primary
          : !fb.ok
          ? Brand.bad
          : typo
          ? Brand.warn
          : Brand.ok;
      final step = _steps[_queue[_pos]];
      final explain = '${step['explain_uz'] ?? ''}';
      final title =
          fb.title ??
          (!fb.ok
              ? "To'g'ri javob:"
              : typo
              ? "Deyarli to'g'ri! Imlosiga e'tibor bering:"
              : _combo >= 3
              ? "🔥 $_combo ta ketma-ket to'g'ri!"
              : _praise[Random().nextInt(_praise.length)]);
      final body =
          fb.note ??
          [
            if (!fb.ok && (fb.right ?? '').isNotEmpty) '**${fb.right}**',
            if (typo) '**${fb.typo}**',
            if (explain.isNotEmpty) explain,
          ].join(' — ');
      return AnimatedContainer(
        duration: const Duration(milliseconds: 250),
        width: double.infinity,
        padding: const EdgeInsets.fromLTRB(18, 16, 18, 16),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.13),
          border: Border(top: BorderSide(color: color, width: 2)),
        ),
        child: SafeArea(
          top: false,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                children: [
                  Icon(
                    !fb.graded
                        ? Icons.info_rounded
                        : fb.ok
                        ? Icons.check_circle_rounded
                        : Icons.cancel_rounded,
                    color: color,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      title,
                      style: TextStyle(color: color, fontWeight: FontWeight.w900, fontSize: 17),
                    ),
                  ),
                ],
              ),
              if (body.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Text.rich(md(body, TextStyle(fontSize: 15, height: 1.4, color: scheme.onSurface))),
                ),
              const SizedBox(height: 12),
              FilledButton(
                style: FilledButton.styleFrom(backgroundColor: color),
                onPressed: _next,
                child: const Text('Davom etish'),
              ),
            ],
          ),
        ),
      );
    }
    final ctl = _ctl;
    final isExercise = ctl.isExercise;
    return Container(
      padding: const EdgeInsets.fromLTRB(18, 10, 18, 14),
      decoration: BoxDecoration(
        border: Border(top: BorderSide(color: scheme.outlineVariant.withValues(alpha: 0.5))),
      ),
      child: SafeArea(
        top: false,
        child: Row(
          children: [
            if (ctl.hint != null) ...[
              OutlinedButton.icon(
                onPressed: ctl.hint,
                icon: const Icon(Icons.lightbulb_outline_rounded),
                label: const Text('Yordam'),
              ),
              const SizedBox(width: 10),
            ],
            if (ctl.skippable) ...[
              OutlinedButton(onPressed: _next, child: const Text("O'tkazish")),
              const SizedBox(width: 10),
            ],
            Expanded(
              child: FilledButton(
                onPressed: _checking || (isExercise && !ctl.ready) || (ctl.skippable && !isExercise) ? null : _check,
                child: _checking
                    ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.5))
                    : Text(isExercise ? 'Tekshirish' : 'Davom etish'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _finishView() {
    final r = _result;
    final score = _score;
    final scheme = Theme.of(context).colorScheme;
    final emoji = score >= 90
        ? '🏆'
        : score >= 70
        ? '🎉'
        : '💪';
    final title = score >= 90
        ? 'Mukammal!'
        : score >= 70
        ? (widget.practice ? 'Mashq tugallandi!' : 'Dars tugallandi!')
        : 'Har bir xato — yangi bilim!';
    final next = widget.data['next_slug'] as String?;
    return Confetti(
      active: r != null && score >= 70,
      child: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          const SizedBox(height: 20),
          Center(
            child: TweenAnimationBuilder<double>(
              tween: Tween(begin: 0.3, end: 1),
              duration: const Duration(milliseconds: 700),
              curve: Curves.elasticOut,
              builder: (_, v, child) => Transform.scale(scale: v, child: child),
              child: Text(emoji, style: const TextStyle(fontSize: 88)),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            title,
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w900),
          ),
          Text(
            '${widget.data['title_uz'] ?? (widget.practice ? 'Aralash mashq' : '')}',
            textAlign: TextAlign.center,
            style: TextStyle(color: scheme.outline),
          ),
          const SizedBox(height: 24),
          Row(
            children: [
              _stat('Natija', '$score%', Brand.ok),
              const SizedBox(width: 10),
              _stat('XP', r == null ? '…' : '+${r['xp'] ?? 0}', Brand.warn),
              const SizedBox(width: 10),
              widget.practice
                  ? _stat('Qolgan xatolar', r == null ? '…' : '${r['mistakes_left'] ?? 0}', Brand.flame)
                  : _stat("Yangi so'zlar", r == null ? '…' : '+${r['words_added'] ?? 0}', Brand.primary),
            ],
          ),
          if (r != null && (r['streak'] ?? 0) > 0)
            Padding(
              padding: const EdgeInsets.only(top: 14),
              child: Text(
                '🔥 ${r['streak']} kunlik seriya!',
                textAlign: TextAlign.center,
                style: const TextStyle(fontWeight: FontWeight.w800, color: Brand.flame),
              ),
            ),
          if (_saving)
            const Padding(
              padding: EdgeInsets.all(16),
              child: Center(child: CircularProgressIndicator()),
            ),
          if (_saveError != null)
            Card(
              color: Brand.badSoft,
              margin: const EdgeInsets.only(top: 16),
              child: ListTile(
                title: Text(
                  _saveError is ApiException ? '$_saveError' : 'Natija saqlanmadi',
                  style: const TextStyle(color: Brand.bad),
                ),
                trailing: TextButton(onPressed: _finish, child: const Text('Qayta')),
              ),
            ),
          if (_mistakes.isNotEmpty) ...[
            const SectionTitle('Xatolar ustida ishlang'),
            for (final e in _mistakes.entries)
              Card(
                margin: const EdgeInsets.only(bottom: 8),
                child: ListTile(
                  title: Text(_describe(_steps[e.key]), maxLines: 2, overflow: TextOverflow.ellipsis),
                  subtitle: e.value.isEmpty
                      ? null
                      : Text(
                          '✓ ${e.value}',
                          style: const TextStyle(color: Brand.ok, fontWeight: FontWeight.w700),
                        ),
                ),
              ),
          ],
          const SizedBox(height: 24),
          if (!widget.practice && next != null && r != null)
            FilledButton.icon(
              onPressed: () =>
                  Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => LessonScreen.lesson(next))),
              icon: const Icon(Icons.arrow_forward_rounded),
              label: const Text('Keyingi dars'),
            ),
          const SizedBox(height: 10),
          OutlinedButton(onPressed: () => Navigator.pop(context), child: const Text('Darslarga qaytish')),
        ],
      ),
    );
  }

  String _describe(Map<String, dynamic> s) =>
      '${s['q'] ?? s['text'] ?? s['uz'] ?? (s['type'] == 'match' ? 'Juftliklar' : 'Mashq')}'.replaceAll('**', '');

  Widget _stat(String label, String value, Color color) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 16),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: color.withValues(alpha: 0.4), width: 1.5),
        ),
        child: Column(
          children: [
            Text(
              value,
              style: TextStyle(fontSize: 24, fontWeight: FontWeight.w900, color: color),
            ),
            const SizedBox(height: 2),
            Text(label, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
          ],
        ),
      ),
    );
  }
}
