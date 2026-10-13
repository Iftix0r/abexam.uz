import 'package:flutter/material.dart';

import '../core/app_state.dart';
import '../core/theme.dart';
import '../widgets/common.dart';

/// Level test: blocks from A1 upward; stops at the first block not passed.
class PlacementScreen extends StatelessWidget {
  const PlacementScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final api = AppScope.read(context).api;
    return Scaffold(
      appBar: AppBar(title: const Text('Darajani aniqlash')),
      body: Loader<Map<String, dynamic>>(
        load: () => api.get('placement/'),
        builder: (context, test, _) => _Test(test: test),
      ),
    );
  }
}

class _Test extends StatefulWidget {
  const _Test({required this.test});

  final Map<String, dynamic> test;

  @override
  State<_Test> createState() => _TestState();
}

class _TestState extends State<_Test> {
  int _block = 0;
  int _q = 0;
  int? _sel;
  final _answers = <String, List<int>>{};
  String? _level;
  bool _started = false;

  List<Map<String, dynamic>> get _blocks => (widget.test['blocks'] as List).cast<Map<String, dynamic>>();
  int get _passMark => (widget.test['pass_mark'] as int?) ?? 4;

  Future<void> _submit() async {
    final state = AppScope.read(context);
    try {
      final r = await state.api.post('placement/', {'answers': _answers});
      await state.refresh();
      if (mounted) setState(() => _level = '${r['level']}');
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  void _answer() {
    final block = _blocks[_block];
    final questions = (block['questions'] as List).cast<Map<String, dynamic>>();
    (_answers['$_block'] ??= []).add(_sel!);
    _sel = null;
    if (_q + 1 < questions.length) {
      setState(() => _q++);
      return;
    }
    final right = [for (var i = 0; i < questions.length; i++) _answers['$_block']![i] == questions[i]['answer']].where((v) => v).length;
    if (right < _passMark || _block + 1 >= _blocks.length) {
      setState(() => _q = questions.length);
      _submit();
    } else {
      setState(() {
        _block++;
        _q = 0;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    if (!_started) {
      return Padding(
        padding: const EdgeInsets.all(24),
        child: Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          const Text('🎯', textAlign: TextAlign.center, style: TextStyle(fontSize: 80)),
          const SizedBox(height: 12),
          const Text('Qaysi darajadan boshlaysiz?', textAlign: TextAlign.center, style: TextStyle(fontSize: 24, fontWeight: FontWeight.w900)),
          const SizedBox(height: 10),
          Text("Savollar oson boshlanib, asta qiyinlashadi. Bilmasangiz — taxmin qilmang, eng yaqin javobni tanlang. Taxminan 5 daqiqa.",
              textAlign: TextAlign.center, style: TextStyle(color: scheme.outline, fontSize: 15)),
          const SizedBox(height: 28),
          FilledButton(onPressed: () => setState(() => _started = true), child: const Text('Boshlash')),
        ]),
      );
    }
    if (_level != null) {
      return Padding(
        padding: const EdgeInsets.all(24),
        child: Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          const Text('🎉', textAlign: TextAlign.center, style: TextStyle(fontSize: 80)),
          const Text('Sizning darajangiz', textAlign: TextAlign.center, style: TextStyle(fontSize: 18)),
          Text(_level!, textAlign: TextAlign.center, style: TextStyle(fontSize: 64, fontWeight: FontWeight.w900, color: Brand.level(_level!))),
          const SizedBox(height: 8),
          Text("Darslar shu darajadan ochildi. Xohlasangiz, istalgan vaqtda boshqa darajani tanlashingiz mumkin.",
              textAlign: TextAlign.center, style: TextStyle(color: scheme.outline)),
          const SizedBox(height: 28),
          FilledButton(onPressed: () => Navigator.pop(context), child: const Text("O'qishni boshlash")),
        ]),
      );
    }
    final block = _blocks[_block];
    final questions = (block['questions'] as List).cast<Map<String, dynamic>>();
    if (_q >= questions.length) return const Center(child: CircularProgressIndicator());
    final q = questions[_q];
    final options = (q['options'] as List).map((e) => '$e').toList();
    final total = _blocks.fold<int>(0, (n, b) => n + (b['questions'] as List).length);
    final done = _blocks.take(_block).fold<int>(0, (n, b) => n + (b['questions'] as List).length) + _q;
    return Padding(
      padding: const EdgeInsets.all(18),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        LinearProgressIndicator(value: done / total, minHeight: 8, borderRadius: BorderRadius.circular(8)),
        const SizedBox(height: 18),
        Row(children: [Pill(label: '${block['level']}', color: Brand.level('${block['level']}'))]),
        const SizedBox(height: 14),
        if (q['audio'] == true && q['say'] != null) ...[PlayButtons('${q['say']}'), const SizedBox(height: 18)],
        Text('${q['q']}', style: const TextStyle(fontSize: 21, fontWeight: FontWeight.w800)),
        const SizedBox(height: 18),
        for (var i = 0; i < options.length; i++)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Material(
              color: _sel == i ? scheme.primary.withValues(alpha: 0.1) : Theme.of(context).cardTheme.color,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
                side: BorderSide(width: 2, color: _sel == i ? scheme.primary : scheme.outlineVariant),
              ),
              child: InkWell(
                borderRadius: BorderRadius.circular(16),
                onTap: () => setState(() => _sel = i),
                child: Padding(padding: const EdgeInsets.all(15), child: Text(options[i], style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600))),
              ),
            ),
          ),
        const Spacer(),
        FilledButton(onPressed: _sel == null ? null : _answer, child: const Text('Keyingisi')),
      ]),
    );
  }
}
