import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import '../../core/speech.dart';
import '../../core/text.dart';
import '../../core/theme.dart';
import '../../widgets/common.dart';

/// Small coloured label above every step ("Yangi so'zlar", "Dialog"...).
class Kicker extends StatelessWidget {
  const Kicker(this.icon, this.text, {super.key, this.color});

  final IconData icon;
  final String text;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final c = color ?? Theme.of(context).colorScheme.primary;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(children: [
        Icon(icon, size: 18, color: c),
        const SizedBox(width: 6),
        Text(text.toUpperCase(), style: TextStyle(color: c, fontWeight: FontWeight.w800, fontSize: 12, letterSpacing: 1.1)),
      ]),
    );
  }
}

class StepTitle extends StatelessWidget {
  const StepTitle(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) {
    final base = TextStyle(fontSize: 21, fontWeight: FontWeight.w800, height: 1.3, color: Theme.of(context).colorScheme.onSurface);
    return Padding(padding: const EdgeInsets.only(bottom: 8), child: Text.rich(md(text, base)));
  }
}

class StepSub extends StatelessWidget {
  const StepSub(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 14),
        child: Text(text, style: TextStyle(color: Theme.of(context).colorScheme.outline, fontSize: 15, height: 1.4)),
      );
}

// ── words ────────────────────────────────────────────────────────────────
class WordsStep extends StatefulWidget {
  const WordsStep({super.key, required this.words});

  final List<Map<String, dynamic>> words;

  @override
  State<WordsStep> createState() => _WordsStepState();
}

class _WordsStepState extends State<WordsStep> {
  final _heard = <int>{};

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker(Icons.auto_awesome_rounded, "Yangi so'zlar"),
      StepTitle("Bu darsda ${widget.words.length} ta yangi so'z bor"),
      const StepSub("Kartochkani bosib tinglang va ovoz chiqarib takrorlang. Yodlash shart emas — so'zlar darsda qayta uchraydi."),
      for (var i = 0; i < widget.words.length; i++)
        Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: Card(
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(16),
              side: BorderSide(color: _heard.contains(i) ? Brand.ok.withValues(alpha: 0.5) : scheme.outlineVariant),
            ),
            child: InkWell(
              borderRadius: BorderRadius.circular(16),
              onTap: () {
                setState(() => _heard.add(i));
                Speech.instance.say('${widget.words[i]['en']}', rate: 0.85);
              },
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(children: [
                    Expanded(
                      child: Wrap(crossAxisAlignment: WrapCrossAlignment.end, spacing: 8, children: [
                        Text('${widget.words[i]['en']}', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
                        if ((widget.words[i]['ipa'] ?? '').toString().isNotEmpty)
                          Text('${widget.words[i]['ipa']}', style: TextStyle(color: scheme.outline, fontSize: 13)),
                      ]),
                    ),
                    Icon(_heard.contains(i) ? Icons.check_circle_rounded : Icons.volume_up_rounded,
                        color: _heard.contains(i) ? Brand.ok : scheme.primary),
                  ]),
                  const SizedBox(height: 4),
                  Text('${widget.words[i]['uz']}', style: TextStyle(color: scheme.primary, fontWeight: FontWeight.w600)),
                  if ((widget.words[i]['ex'] ?? '').toString().isNotEmpty) ...[
                    const SizedBox(height: 6),
                    Row(children: [
                      Expanded(
                        child: Text('${widget.words[i]['ex']}',
                            style: TextStyle(fontStyle: FontStyle.italic, color: scheme.onSurfaceVariant)),
                      ),
                      SayButton('${widget.words[i]['ex']}', size: 18),
                    ]),
                  ],
                ]),
              ),
            ),
          ),
        ),
    ]);
  }
}

// ── dialogue ─────────────────────────────────────────────────────────────
class DialogueStep extends StatefulWidget {
  const DialogueStep({super.key, required this.step});

  final Map<String, dynamic> step;

  @override
  State<DialogueStep> createState() => _DialogueStepState();
}

class _DialogueStepState extends State<DialogueStep> {
  bool _uz = false;
  int _playing = -1;
  int _run = 0;

  List<Map<String, dynamic>> get _lines => (widget.step['lines'] as List).cast<Map<String, dynamic>>();

  Future<void> _playAll() async {
    final my = ++_run;
    for (var i = 0; i < _lines.length; i++) {
      if (!mounted || my != _run) return;
      setState(() => _playing = i);
      await Speech.instance.say('${_lines[i]['en']}');
      await Future.delayed(const Duration(milliseconds: 300));
    }
    if (mounted && my == _run) setState(() => _playing = -1);
  }

  @override
  void dispose() {
    _run++;
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final speakers = <String>[];
    for (final l in _lines) {
      if (!speakers.contains(l['who'])) speakers.add('${l['who']}');
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker(Icons.forum_rounded, 'Dialog'),
      StepTitle('${widget.step['title'] ?? ''}'),
      if (widget.step['context_uz'] != null) StepSub('${widget.step['context_uz']}'),
      Wrap(spacing: 8, children: [
        FilledButton.tonalIcon(onPressed: _playAll, icon: const Icon(Icons.play_arrow_rounded), label: const Text('Hammasini tinglash')),
        FilterChip(label: const Text('Tarjima'), selected: _uz, onSelected: (v) => setState(() => _uz = v)),
      ]),
      const SizedBox(height: 14),
      for (var i = 0; i < _lines.length; i++)
        Builder(builder: (context) {
          final mine = speakers.indexOf('${_lines[i]['who']}') % 2 == 1;
          final playing = _playing == i;
          return Align(
            alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
            child: GestureDetector(
              onTap: () {
                _run++;
                setState(() => _playing = i);
                Speech.instance.say('${_lines[i]['en']}').then((_) {
                  if (mounted && _playing == i) setState(() => _playing = -1);
                });
              },
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                margin: const EdgeInsets.only(bottom: 10),
                padding: const EdgeInsets.all(12),
                constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width * 0.8),
                decoration: BoxDecoration(
                  color: mine ? scheme.primary.withValues(alpha: playing ? 0.25 : 0.12) : (playing ? Brand.warnSoft : Theme.of(context).cardTheme.color),
                  borderRadius: BorderRadius.only(
                    topLeft: const Radius.circular(18),
                    topRight: const Radius.circular(18),
                    bottomLeft: Radius.circular(mine ? 18 : 4),
                    bottomRight: Radius.circular(mine ? 4 : 18),
                  ),
                  border: Border.all(color: playing ? Brand.warn : scheme.outlineVariant.withValues(alpha: 0.6)),
                ),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('${_lines[i]['who']}', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w800, color: scheme.primary)),
                  const SizedBox(height: 2),
                  Text('${_lines[i]['en']}', style: TextStyle(fontSize: 16, height: 1.35, color: playing ? Colors.black87 : null)),
                  if (_uz && (_lines[i]['uz'] ?? '').toString().isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Text('${_lines[i]['uz']}', style: TextStyle(fontSize: 13, color: scheme.outline)),
                  ],
                ]),
              ),
            ),
          );
        }),
      const SizedBox(height: 6),
      StepSub("Avval tarjimasiz tushunishga harakat qiling. Gapni bosing — qayta eshitasiz."),
    ]);
  }
}

// ── reading ──────────────────────────────────────────────────────────────
class ReadingStep extends StatefulWidget {
  const ReadingStep({super.key, required this.step});

  final Map<String, dynamic> step;

  @override
  State<ReadingStep> createState() => _ReadingStepState();
}

class _ReadingStepState extends State<ReadingStep> {
  bool _uz = false;
  String? _gloss;
  final _recognizers = <TapGestureRecognizer>[];

  @override
  void dispose() {
    for (final r in _recognizers) {
      r.dispose();
    }
    super.dispose();
  }

  /// Text with glossary words underlined and tappable (first occurrence each).
  List<InlineSpan> _spans(String text, Map<String, String> glossary, Color color) {
    final taken = <(int, int, String)>[];
    final keys = glossary.keys.toList()..sort((a, b) => b.length.compareTo(a.length));
    final lower = text.toLowerCase();
    for (final k in keys) {
      final re = RegExp(r'(?<![\p{L}])' + RegExp.escape(k.toLowerCase()) + r'(?![\p{L}])', unicode: true);
      for (final m in re.allMatches(lower)) {
        if (taken.any((t) => m.start < t.$2 && m.end > t.$1)) continue;
        taken.add((m.start, m.end, k));
        break;
      }
    }
    taken.sort((a, b) => a.$1.compareTo(b.$1));
    for (final r in _recognizers) {
      r.dispose();
    }
    _recognizers.clear();
    final spans = <InlineSpan>[];
    var last = 0;
    for (final t in taken) {
      if (t.$1 > last) spans.add(TextSpan(text: text.substring(last, t.$1)));
      final rec = TapGestureRecognizer()..onTap = () => setState(() => _gloss = '${t.$3} — ${glossary[t.$3]}');
      _recognizers.add(rec);
      spans.add(TextSpan(
        text: text.substring(t.$1, t.$2),
        recognizer: rec,
        style: TextStyle(
          decoration: TextDecoration.underline,
          decorationStyle: TextDecorationStyle.dotted,
          decorationColor: color,
          color: color,
          fontWeight: FontWeight.w600,
        ),
      ));
      last = t.$2;
    }
    if (last < text.length) spans.add(TextSpan(text: text.substring(last)));
    return spans;
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.step;
    final scheme = Theme.of(context).colorScheme;
    final glossary = ((s['glossary'] as Map?) ?? {}).map((k, v) => MapEntry('$k', '$v'));
    final text = '${s['text'] ?? ''}';
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker(Icons.menu_book_rounded, "O'qish"),
      StepTitle('${s['title'] ?? ''}'),
      Wrap(spacing: 8, children: [
        FilledButton.tonalIcon(onPressed: () => Speech.instance.say(text, rate: 0.95), icon: const Icon(Icons.play_arrow_rounded), label: const Text('Tinglash')),
        if (s['uz'] != null) FilterChip(label: const Text("To'liq tarjima"), selected: _uz, onSelected: (v) => setState(() => _uz = v)),
      ]),
      const SizedBox(height: 14),
      Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Text.rich(
            TextSpan(style: TextStyle(fontSize: 17, height: 1.6, color: scheme.onSurface), children: _spans(text, glossary, scheme.primary)),
          ),
        ),
      ),
      AnimatedSize(
        duration: const Duration(milliseconds: 200),
        child: _gloss == null
            ? const SizedBox(width: double.infinity)
            : Container(
                width: double.infinity,
                margin: const EdgeInsets.only(top: 10),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(color: scheme.primary.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(12)),
                child: Row(children: [
                  Icon(Icons.translate_rounded, color: scheme.primary, size: 18),
                  const SizedBox(width: 8),
                  Expanded(child: Text(_gloss!, style: const TextStyle(fontWeight: FontWeight.w600))),
                ]),
              ),
      ),
      if (_uz)
        Padding(
          padding: const EdgeInsets.only(top: 12),
          child: Text('${s['uz']}', style: TextStyle(color: scheme.outline, height: 1.5)),
        ),
      const SizedBox(height: 10),
      const StepSub("Rangli so'zlarni bosing — tarjimasi chiqadi. Asosiy ma'noni tushunsangiz yetarli."),
    ]);
  }
}

// ── grammar / tip ────────────────────────────────────────────────────────
class GrammarCard extends StatelessWidget {
  const GrammarCard({super.key, required this.step});

  final Map<String, dynamic> step;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final base = TextStyle(fontSize: 15.5, height: 1.5, color: scheme.onSurface);
    final examples = ((step['examples'] as List?) ?? []).cast<Map>();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            for (final p in '${step['body_uz'] ?? ''}'.split('\n'))
              Padding(padding: const EdgeInsets.only(bottom: 8), child: Text.rich(md(p, base, strongColor: scheme.primary))),
          ]),
        ),
      ),
      if (examples.isNotEmpty) ...[
        const SizedBox(height: 12),
        for (final e in examples)
          Container(
            margin: const EdgeInsets.only(bottom: 8),
            padding: const EdgeInsets.fromLTRB(14, 10, 6, 10),
            decoration: BoxDecoration(
              border: Border(left: BorderSide(color: scheme.primary, width: 4)),
              color: scheme.primary.withValues(alpha: 0.06),
              borderRadius: const BorderRadius.horizontal(right: Radius.circular(12)),
            ),
            child: Row(children: [
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('${e['en']}', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15.5)),
                  Text('${e['uz'] ?? ''}', style: TextStyle(color: scheme.outline, fontSize: 13.5)),
                ]),
              ),
              SayButton('${e['en']}', size: 18),
            ]),
          ),
      ],
    ]);
  }
}

class GrammarStep extends StatelessWidget {
  const GrammarStep({super.key, required this.step, this.tip = false});

  final Map<String, dynamic> step;
  final bool tip;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Kicker(tip ? Icons.info_rounded : Icons.lightbulb_rounded, tip ? 'Maslahat' : 'Grammatika', color: tip ? Brand.warn : null),
      StepTitle('${step['title_uz'] ?? ''}'),
      GrammarCard(step: step),
    ]);
  }
}
