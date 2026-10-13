import 'dart:math';

import 'package:flutter/material.dart';

import '../core/app_state.dart';
import '../core/speech.dart';
import '../core/theme.dart';
import '../widgets/common.dart';

/// Vocabulary deck with spaced repetition (server: learn/srs.py).
class ReviewTab extends StatefulWidget {
  const ReviewTab({super.key, required this.active});

  final bool active;

  @override
  State<ReviewTab> createState() => _ReviewTabState();
}

class _ReviewTabState extends State<ReviewTab> {
  Key _reload = UniqueKey();

  @override
  void didUpdateWidget(ReviewTab old) {
    super.didUpdateWidget(old);
    if (widget.active && !old.active) _reload = UniqueKey();
  }

  @override
  Widget build(BuildContext context) {
    final api = AppScope.of(context).api;
    return SafeArea(
      child: Loader<Map<String, dynamic>>(
        key: _reload,
        load: () => api.get('review/'),
        builder: (context, data, reload) {
          final counts = (data['counts'] as Map).cast<String, dynamic>();
          final cards = (data['cards'] as List).cast<Map<String, dynamic>>();
          return RefreshIndicator(
            onRefresh: reload,
            child: ListView(padding: const EdgeInsets.all(16), children: [
              const Text("So'zlarni takrorlash", style: TextStyle(fontSize: 26, fontWeight: FontWeight.w900)),
              const SizedBox(height: 4),
              Text("Darslardagi so'zlar shu yerga tushadi. Unutish arafasidagi so'zlar o'z vaqtida qayta chiqadi.",
                  style: TextStyle(color: Theme.of(context).colorScheme.outline)),
              const SizedBox(height: 18),
              Row(children: [
                _count('Takrorlash', counts['due'], Brand.flame),
                const SizedBox(width: 10),
                _count('Yangi', counts['new'], Brand.primary),
                const SizedBox(width: 10),
                _count("O'rganilgan", counts['learned'], Brand.ok),
              ]),
              const SizedBox(height: 22),
              if (cards.isEmpty)
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(children: [
                      const Text('✅', style: TextStyle(fontSize: 52)),
                      const SizedBox(height: 8),
                      Text(
                        (counts['total'] ?? 0) == 0
                            ? "Hali so'z yo'q. Dars o'ting — yangi so'zlar avtomatik qo'shiladi."
                            : "Bugungi takrorlash tugadi! Ertaga yana keling.",
                        textAlign: TextAlign.center,
                        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                      ),
                    ]),
                  ),
                )
              else
                FilledButton.icon(
                  onPressed: () async {
                    await Navigator.of(context).push(MaterialPageRoute(builder: (_) => _Session(cards: cards)));
                    reload();
                    if (context.mounted) AppScope.read(context).refresh().catchError((_) {});
                  },
                  icon: const Icon(Icons.play_arrow_rounded),
                  label: Text('Boshlash · ${cards.length} ta karta'),
                ),
              const SizedBox(height: 12),
              Text("Jami lug'atingizda: ${counts['total'] ?? 0} ta so'z",
                  textAlign: TextAlign.center, style: TextStyle(color: Theme.of(context).colorScheme.outline)),
            ]),
          );
        },
      ),
    );
  }

  Widget _count(String label, dynamic value, Color color) => Expanded(
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 16),
          decoration: BoxDecoration(color: color.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(16)),
          child: Column(children: [
            Text('${value ?? 0}', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w900, color: color)),
            Text(label, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
          ]),
        ),
      );
}

class _Session extends StatefulWidget {
  const _Session({required this.cards});

  final List<Map<String, dynamic>> cards;

  @override
  State<_Session> createState() => _SessionState();
}

class _SessionState extends State<_Session> {
  late final List<Map<String, dynamic>> _queue = [...widget.cards];
  int _pos = 0;
  bool _flipped = false;
  int _remembered = 0;
  bool _sending = false;

  @override
  void initState() {
    super.initState();
    _speak();
  }

  void _speak() {
    if (_pos < _queue.length) Speech.instance.say('${_queue[_pos]['en']}', rate: 0.9);
  }

  Future<void> _grade(int grade) async {
    if (_sending) return;
    final card = _queue[_pos];
    setState(() => _sending = true);
    try {
      await AppScope.read(context).api.post('review/grade/', {'id': card['id'], 'grade': grade});
      if (grade == 0) {
        _queue.add(card);
      } else {
        _remembered++;
      }
      setState(() {
        _pos++;
        _flipped = false;
      });
      _speak();
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final done = _pos >= _queue.length;
    return Scaffold(
      appBar: AppBar(
        title: Text(done ? 'Tugadi' : '${min(_pos + 1, _queue.length)} / ${_queue.length}'),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(6),
          child: LinearProgressIndicator(value: _queue.isEmpty ? 1 : _pos / _queue.length, color: Brand.ok),
        ),
      ),
      body: SafeArea(
        child: done
            ? Center(
                child: Padding(
                  padding: const EdgeInsets.all(28),
                  child: Column(mainAxisSize: MainAxisSize.min, children: [
                    const Text('🧠', style: TextStyle(fontSize: 80)),
                    const SizedBox(height: 10),
                    const Text('Barakalla!', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w900)),
                    const SizedBox(height: 6),
                    Text("$_remembered ta so'z takrorlandi", style: TextStyle(color: scheme.outline, fontSize: 16)),
                    const SizedBox(height: 28),
                    FilledButton(onPressed: () => Navigator.pop(context), child: const Text('Tayyor')),
                  ]),
                ),
              )
            : Padding(
                padding: const EdgeInsets.all(18),
                child: Column(children: [
                  Expanded(child: _card(_queue[_pos], scheme)),
                  const SizedBox(height: 16),
                  if (!_flipped)
                    FilledButton(onPressed: () => setState(() => _flipped = true), child: const Text("Javobni ko'rsatish"))
                  else
                    Row(children: [
                      _gradeBtn('Yana', "10 daq", Brand.bad, 0),
                      _gradeBtn('Qiyin', '', Brand.warn, 1),
                      _gradeBtn('Yaxshi', '', Brand.ok, 2),
                      _gradeBtn('Oson', '', Brand.primary, 3),
                    ]),
                ]),
              ),
      ),
    );
  }

  Widget _card(Map<String, dynamic> c, ColorScheme scheme) {
    return GestureDetector(
      onTap: () => setState(() => _flipped = true),
      child: AnimatedSwitcher(
        duration: const Duration(milliseconds: 300),
        transitionBuilder: (child, a) => ScaleTransition(scale: Tween(begin: 0.92, end: 1.0).animate(a), child: FadeTransition(opacity: a, child: child)),
        child: Container(
          key: ValueKey('$_pos-$_flipped'),
          width: double.infinity,
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: Theme.of(context).cardTheme.color,
            borderRadius: BorderRadius.circular(28),
            border: Border.all(color: scheme.outlineVariant),
            boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.06), blurRadius: 24, offset: const Offset(0, 10))],
          ),
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
            if (c['new'] == true) const Pill(label: "Yangi so'z", color: Brand.primary),
            const SizedBox(height: 14),
            Text('${c['en']}', textAlign: TextAlign.center, style: const TextStyle(fontSize: 32, fontWeight: FontWeight.w900)),
            const SizedBox(height: 8),
            SayButton('${c['en']}', size: 26),
            if (_flipped) ...[
              const Divider(height: 36),
              Text('${c['uz']}', textAlign: TextAlign.center, style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700, color: scheme.primary)),
              if ('${c['ex'] ?? ''}'.isNotEmpty) ...[
                const SizedBox(height: 14),
                Text('${c['ex']}', textAlign: TextAlign.center, style: TextStyle(fontStyle: FontStyle.italic, color: scheme.onSurfaceVariant, fontSize: 16)),
              ],
            ] else ...[
              const SizedBox(height: 24),
              Text("Ma'nosini eslang, keyin kartani bosing", style: TextStyle(color: scheme.outline)),
            ],
          ]),
        ),
      ),
    );
  }

  Widget _gradeBtn(String label, String sub, Color color, int grade) {
    return Expanded(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 4),
        child: FilledButton(
          style: FilledButton.styleFrom(backgroundColor: color, padding: EdgeInsets.zero, minimumSize: const Size(0, 58)),
          onPressed: _sending ? null : () => _grade(grade),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Text(label, style: const TextStyle(fontWeight: FontWeight.w800)),
            if (sub.isNotEmpty) Text(sub, style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w500)),
          ]),
        ),
      ),
    );
  }
}
