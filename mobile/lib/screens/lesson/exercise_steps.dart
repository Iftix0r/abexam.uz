import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api.dart';
import '../../core/speech.dart';
import '../../core/text.dart';
import '../../core/theme.dart';
import '../../widgets/common.dart';
import 'input_steps.dart';
import 'step_ctl.dart';

// ── choice ───────────────────────────────────────────────────────────────
class ChoiceStep extends StatefulWidget {
  const ChoiceStep({super.key, required this.step, required this.ctl, required this.env});

  final Map<String, dynamic> step;
  final StepCtl ctl;
  final StepEnv env;

  @override
  State<ChoiceStep> createState() => _ChoiceStepState();
}

class _ChoiceStepState extends State<ChoiceStep> {
  int? _sel;
  bool _revealed = false;
  bool _quz = false;
  final _gone = <int>{};

  List<String> get _options => (widget.step['options'] as List).map((e) => '$e').toList();
  int get _answer => widget.step['answer'] as int;
  String? get _say => widget.step['audio'] == true ? widget.step['say'] as String? : null;

  @override
  void initState() {
    super.initState();
    widget.ctl.configure(
      check: () async {
        setState(() => _revealed = true);
        return Outcome(ok: _sel == _answer, right: _options[_answer]);
      },
      hint: _hint,
    );
    if (_say != null) {
      Future.delayed(const Duration(milliseconds: 450), () => mounted ? Speech.instance.say(_say!) : null);
    }
  }

  void _hint() {
    final wrong = shuffled([
      for (var i = 0; i < _options.length; i++)
        if (i != _answer && !_gone.contains(i)) i,
    ]);
    if (wrong.length > 1) {
      setState(() {
        _gone.add(wrong.first);
        if (_sel == wrong.first) {
          _sel = null;
          widget.ctl.setReady(false);
        }
      });
    }
    if (_say != null) Speech.instance.say(_say!, rate: 0.65);
    if (wrong.length <= 2) widget.ctl.dropHint();
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.step;
    final scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Kicker(
          _say != null ? Icons.headphones_rounded : Icons.checklist_rounded,
          _say != null ? 'Tinglab tushunish' : "To'g'ri javobni tanlang",
        ),
        if (_say != null) ...[const SizedBox(height: 6), PlayButtons(_say!), const SizedBox(height: 20)],
        if ('${s['q']}'.contains('**'))
          StepTitle('${s['q'] ?? ''}')
        else
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: GlossText(
              '${s['q'] ?? ''}',
              dict: widget.env.dict,
              style: TextStyle(fontSize: 21, fontWeight: FontWeight.w800, height: 1.3, color: scheme.onSurface),
            ),
          ),
        if (s['q_uz'] != null)
          TextButton(
            onPressed: () => setState(() => _quz = true),
            child: Text(_quz ? '${s['q_uz']}' : 'Savol tarjimasi'),
          ),
        const SizedBox(height: 8),
        for (var i = 0; i < _options.length; i++)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: _OptionTile(
              text: _options[i],
              selected: _sel == i,
              gone: _gone.contains(i),
              state: !_revealed
                  ? null
                  : i == _answer
                  ? true
                  : (i == _sel ? false : null),
              onTap: _revealed || _gone.contains(i)
                  ? null
                  : () {
                      setState(() => _sel = i);
                      widget.ctl.setReady(true);
                    },
              accent: scheme.primary,
            ),
          ),
      ],
    );
  }
}

class _OptionTile extends StatelessWidget {
  const _OptionTile({
    required this.text,
    required this.selected,
    required this.gone,
    required this.state,
    required this.onTap,
    required this.accent,
  });

  final String text;
  final bool selected;
  final bool gone;

  /// null — neutral, true — correct, false — wrong pick.
  final bool? state;
  final VoidCallback? onTap;
  final Color accent;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final border = state == true
        ? Brand.ok
        : state == false
        ? Brand.bad
        : selected
        ? accent
        : scheme.outlineVariant;
    final fill = state == true
        ? Brand.okSoft
        : state == false
        ? Brand.badSoft
        : selected
        ? accent.withValues(alpha: 0.1)
        : Theme.of(context).cardTheme.color;
    return AnimatedOpacity(
      duration: const Duration(milliseconds: 200),
      opacity: gone ? 0.35 : 1,
      child: Material(
        color: fill,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(color: border, width: 2),
        ),
        child: InkWell(
          borderRadius: BorderRadius.circular(16),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 15),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    text,
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                      decoration: gone ? TextDecoration.lineThrough : null,
                      color: state != null ? Colors.black87 : null,
                    ),
                  ),
                ),
                if (state == true) const Icon(Icons.check_circle_rounded, color: Brand.ok),
                if (state == false) const Icon(Icons.cancel_rounded, color: Brand.bad),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ── gap ──────────────────────────────────────────────────────────────────
class GapStep extends StatefulWidget {
  const GapStep({super.key, required this.step, required this.ctl, required this.env});

  final Map<String, dynamic> step;
  final StepCtl ctl;
  final StepEnv env;

  @override
  State<GapStep> createState() => _GapStepState();
}

class _GapStepState extends State<GapStep> {
  final _input = TextEditingController();
  int _shown = 0;

  String get _first => answersOf(widget.step['answer']).first;

  @override
  void initState() {
    super.initState();
    _input.addListener(() {
      widget.ctl.setReady(_input.text.trim().isNotEmpty);
      setState(() {});
    });
    widget.ctl.configure(
      check: () async {
        final g = grade(_input.text, widget.step['answer']);
        return Outcome(ok: g.ok, typo: g.typo, right: _first);
      },
      hint: () {
        // Reveal the answer letter by letter, never the whole word.
        _shown = (_shown + (_first.length / 3).ceil().clamp(1, 99)).clamp(0, _first.length - 1);
        _input.text = _first.substring(0, _shown);
        _input.selection = TextSelection.collapsed(offset: _input.text.length);
        if (_shown >= _first.length - 1) widget.ctl.dropHint();
      },
    );
  }

  @override
  void dispose() {
    _input.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.step;
    final scheme = Theme.of(context).colorScheme;
    final parts = '${s['text']}'.split('___');
    final filled = _input.text.trim();
    final base = TextStyle(fontSize: 21, height: 1.5, fontWeight: FontWeight.w600, color: scheme.onSurface);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Kicker(Icons.edit_rounded, "Bo'sh joyni to'ldiring"),
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: GlossText.segments(
                [
                  parts.first,
                  TextSpan(
                    text: filled.isEmpty ? ' ______ ' : ' $filled ',
                    style: TextStyle(
                      color: scheme.primary,
                      fontWeight: FontWeight.w800,
                      decoration: TextDecoration.underline,
                    ),
                  ),
                  if (parts.length > 1) parts.sublist(1).join('___'),
                ],
                dict: widget.env.dict,
                style: base,
              ),
            ),
            SayButton('${s['text']}'.replaceAll('___', '...')),
          ],
        ),
        if (s['uz'] != null) Padding(padding: const EdgeInsets.only(top: 8), child: StepSub('${s['uz']}')),
        const SizedBox(height: 12),
        TextField(
          controller: _input,
          enabled: !widget.ctl.answered,
          autofocus: true,
          autocorrect: false,
          enableSuggestions: false,
          textCapitalization: TextCapitalization.none,
          textInputAction: TextInputAction.done,
          onSubmitted: (_) => widget.ctl.submit?.call(),
          style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
          decoration: const InputDecoration(hintText: 'Javobni yozing...'),
        ),
      ],
    );
  }
}

// ── word bank / typed answer (translate, listen, order) ─────────────────
class WordBank extends StatefulWidget {
  const WordBank({super.key, required this.tokens, required this.onChanged, required this.locked});

  final List<String> tokens;
  final ValueChanged<String> onChanged;
  final bool locked;

  @override
  State<WordBank> createState() => WordBankState();
}

class WordBankState extends State<WordBank> {
  final _picked = <int>[];
  late final List<int> _order = shuffled(List.generate(widget.tokens.length, (i) => i));

  String get text => _picked.map((i) => widget.tokens[i]).join(' ');
  int get count => _picked.length;

  void _changed() {
    setState(() {});
    widget.onChanged(text);
  }

  /// Hint: keep the correct start, then add the next correct word.
  void placeNext(List<String> answerTokens) {
    var k = 0;
    while (k < _picked.length && k < answerTokens.length && norm(widget.tokens[_picked[k]]) == norm(answerTokens[k])) {
      k++;
    }
    _picked.removeRange(k, _picked.length);
    if (k < answerTokens.length) {
      final want = norm(answerTokens[k]);
      for (var i = 0; i < widget.tokens.length; i++) {
        if (norm(widget.tokens[i]) == want && !_picked.contains(i)) {
          _picked.add(i);
          break;
        }
      }
    }
    _changed();
  }

  Widget _chip(int i, {required bool inLine}) {
    final used = !inLine && _picked.contains(i);
    final scheme = Theme.of(context).colorScheme;
    return AnimatedOpacity(
      duration: const Duration(milliseconds: 150),
      opacity: used ? 0.25 : 1,
      child: Material(
        color: Theme.of(context).cardTheme.color,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: scheme.outlineVariant, width: 1.5),
        ),
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: widget.locked || used
              ? null
              : () {
                  if (inLine) {
                    _picked.remove(i);
                  } else {
                    _picked.add(i);
                    Speech.instance.say(widget.tokens[i]);
                  }
                  _changed();
                },
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            child: Text(widget.tokens[i], style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      children: [
        Container(
          constraints: const BoxConstraints(minHeight: 110),
          width: double.infinity,
          padding: const EdgeInsets.symmetric(vertical: 10),
          decoration: BoxDecoration(
            border: Border(bottom: BorderSide(color: scheme.outlineVariant, width: 2)),
          ),
          child: Wrap(spacing: 8, runSpacing: 8, children: [for (final i in _picked) _chip(i, inLine: true)]),
        ),
        const SizedBox(height: 18),
        Wrap(
          alignment: WrapAlignment.center,
          spacing: 8,
          runSpacing: 10,
          children: [for (final i in _order) _chip(i, inLine: false)],
        ),
      ],
    );
  }
}

/// Translate / dictation: typed answer, or tap-the-words mode (default for A1–A2).
class TypedStep extends StatefulWidget {
  const TypedStep({super.key, required this.step, required this.ctl, required this.env, required this.dictation});

  final Map<String, dynamic> step;
  final StepCtl ctl;
  final StepEnv env;
  final bool dictation;

  @override
  State<TypedStep> createState() => _TypedStepState();
}

class _TypedStepState extends State<TypedStep> {
  late bool _bank = widget.env.beginner;
  final _input = TextEditingController();
  final _bankKey = GlobalKey<WordBankState>();
  late final String _answer = answersOf(widget.step['answer']).first;
  late final List<String> _answerTokens = tokensOf(_answer);
  late final List<String> _tokens = _buildTokens();

  List<String> _buildTokens() {
    final exclude = _answerTokens.map(norm).toSet();
    final extra = shuffled(
      widget.env.wordPool.where((w) => !exclude.contains(norm(w))).toSet(),
    ).take((_answerTokens.length / 2).ceil().clamp(2, 4));
    return [..._answerTokens, ...extra];
  }

  String get _value => _bank ? (_bankKey.currentState?.text ?? '') : _input.text;

  @override
  void initState() {
    super.initState();
    _input.addListener(() => widget.ctl.setReady(_input.text.trim().isNotEmpty));
    widget.ctl.configure(
      check: () async {
        final g = grade(_value, widget.step['answer']);
        return Outcome(ok: g.ok, typo: g.typo, right: _answer);
      },
      hint: () {
        if (!_bank) {
          setState(() => _bank = true);
          widget.ctl.setReady(false);
          return;
        }
        _bankKey.currentState?.placeNext(_answerTokens);
      },
    );
    if (widget.dictation) {
      Future.delayed(const Duration(milliseconds: 450), () => mounted ? Speech.instance.say(_answer) : null);
    }
  }

  @override
  void dispose() {
    _input.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.step;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (widget.dictation) ...[
          const Kicker(Icons.headphones_rounded, 'Diktant'),
          const StepTitle('Eshitganingizni yozing'),
          const SizedBox(height: 8),
          PlayButtons(_answer),
          const SizedBox(height: 20),
        ] else ...[
          const Kicker(Icons.translate_rounded, 'Ingliz tiliga tarjima qiling'),
          StepTitle('${s['uz'] ?? ''}'),
          const SizedBox(height: 8),
        ],
        if (_bank)
          WordBank(
            key: _bankKey,
            tokens: _tokens,
            locked: widget.ctl.answered,
            onChanged: (t) => widget.ctl.setReady(t.isNotEmpty),
          )
        else
          TextField(
            controller: _input,
            enabled: !widget.ctl.answered,
            autofocus: true,
            minLines: 2,
            maxLines: 5,
            autocorrect: false,
            enableSuggestions: false,
            keyboardType: TextInputType.text,
            textInputAction: TextInputAction.done,
            onSubmitted: (_) => widget.ctl.submit?.call(),
            style: const TextStyle(fontSize: 18),
            decoration: InputDecoration(
              hintText: widget.dictation ? 'Eshitganingizni inglizcha yozing...' : 'Inglizcha yozing...',
            ),
          ),
        const SizedBox(height: 10),
        Center(
          child: TextButton.icon(
            onPressed: widget.ctl.answered
                ? null
                : () {
                    setState(() => _bank = !_bank);
                    widget.ctl.setReady(false);
                  },
            icon: Icon(_bank ? Icons.keyboard_rounded : Icons.grid_view_rounded),
            label: Text(_bank ? 'Klaviaturada yozish' : "So'zlardan tuzish (osonroq)"),
          ),
        ),
      ],
    );
  }
}

class OrderStep extends StatefulWidget {
  const OrderStep({super.key, required this.step, required this.ctl});

  final Map<String, dynamic> step;
  final StepCtl ctl;

  @override
  State<OrderStep> createState() => _OrderStepState();
}

class _OrderStepState extends State<OrderStep> {
  final _bankKey = GlobalKey<WordBankState>();
  late final List<String> _words = (widget.step['words'] as List).map((e) => '$e').toList();
  late final String _answer = '${widget.step['answer']}';

  @override
  void initState() {
    super.initState();
    widget.ctl.configure(
      check: () async {
        final g = grade(_bankKey.currentState?.text ?? '', _answer);
        if (g.ok) Speech.instance.say(_answer);
        return Outcome(ok: g.ok, typo: g.typo, right: _answer);
      },
      hint: () => _bankKey.currentState?.placeNext(_answer.split(RegExp(r'\s+'))),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Kicker(Icons.extension_rounded, 'Gap tuzing'),
        StepTitle('${widget.step['uz'] ?? ''}'),
        const SizedBox(height: 8),
        WordBank(
          key: _bankKey,
          tokens: _words,
          locked: widget.ctl.answered,
          onChanged: (_) => widget.ctl.setReady((_bankKey.currentState?.count ?? 0) == _words.length),
        ),
      ],
    );
  }
}

// ── match ────────────────────────────────────────────────────────────────
class MatchStep extends StatefulWidget {
  const MatchStep({super.key, required this.step, required this.ctl});

  final Map<String, dynamic> step;
  final StepCtl ctl;

  @override
  State<MatchStep> createState() => _MatchStepState();
}

class _MatchStepState extends State<MatchStep> {
  late final List<List<String>> _pairs = (widget.step['pairs'] as List)
      .map((p) => (p as List).map((e) => '$e').toList())
      .toList();
  late final List<int> _left = shuffled(List.generate(_pairs.length, (i) => i));
  late final List<int> _right = shuffled(List.generate(_pairs.length, (i) => i));
  int? _pickL, _pickR;
  final _done = <int>{};
  int? _flashL, _flashR;
  int _misses = 0;

  void _try() {
    if (_pickL == null || _pickR == null) return;
    final a = _pickL!, b = _pickR!;
    _pickL = _pickR = null;
    if (a == b) {
      _done.add(a);
      if (_done.length == _pairs.length) {
        // One slip in a long list is fine — it's practice, not a trap.
        widget.ctl.resolve(
          Outcome(
            ok: _misses <= 1,
            title: _misses <= 1 ? null : '$_misses ta xato',
            note: _misses <= 1 ? null : "Bu mashq dars oxirida yana bir bor so'raladi.",
          ),
        );
      }
    } else {
      _misses++;
      _flashL = a;
      _flashR = b;
      Timer(const Duration(milliseconds: 450), () {
        if (mounted) setState(() => _flashL = _flashR = null);
      });
    }
  }

  Widget _tile(String text, int i, bool left) {
    final done = _done.contains(i);
    final picked = left ? _pickL == i : _pickR == i;
    final flash = left ? _flashL == i : _flashR == i;
    final scheme = Theme.of(context).colorScheme;
    final border = done
        ? Brand.ok
        : flash
        ? Brand.bad
        : picked
        ? scheme.primary
        : scheme.outlineVariant;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: AnimatedOpacity(
        duration: const Duration(milliseconds: 250),
        opacity: done ? 0.45 : 1,
        child: Material(
          color: done
              ? Brand.okSoft
              : flash
              ? Brand.badSoft
              : picked
              ? scheme.primary.withValues(alpha: 0.1)
              : Theme.of(context).cardTheme.color,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
            side: BorderSide(color: border, width: 2),
          ),
          child: InkWell(
            borderRadius: BorderRadius.circular(14),
            onTap: done
                ? null
                : () {
                    setState(() {
                      if (left) {
                        _pickL = i;
                        Speech.instance.say(text);
                      } else {
                        _pickR = i;
                      }
                      _try();
                    });
                  },
            child: Container(
              constraints: const BoxConstraints(minHeight: 56),
              alignment: Alignment.center,
              padding: const EdgeInsets.all(8),
              child: Text(
                text,
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontWeight: FontWeight.w600,
                  fontSize: 15,
                  color: done || flash ? Colors.black87 : null,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Kicker(Icons.link_rounded, 'Juftlarini toping'),
        const StepTitle('Mos keladiganlarini bosing'),
        const SizedBox(height: 8),
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(child: Column(children: [for (final i in _left) _tile(_pairs[i][0], i, true)])),
            const SizedBox(width: 10),
            Expanded(child: Column(children: [for (final i in _right) _tile(_pairs[i][1], i, false)])),
          ],
        ),
      ],
    );
  }
}

// ── speak ────────────────────────────────────────────────────────────────
class SpeakStep extends StatefulWidget {
  const SpeakStep({super.key, required this.step, required this.ctl});

  final Map<String, dynamic> step;
  final StepCtl ctl;

  @override
  State<SpeakStep> createState() => _SpeakStepState();
}

class _SpeakStepState extends State<SpeakStep> with SingleTickerProviderStateMixin {
  late final AnimationController _pulse = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1200),
  );
  bool _listening = false;
  bool? _available;
  List<bool>? _hits;
  String? _heard;
  String? _status;
  int _tries = 0;

  String get _text => '${widget.step['text']}';

  @override
  void initState() {
    super.initState();
    widget.ctl.configure(skippable: true);
    Speech.instance.canListen.then((v) {
      if (mounted) setState(() => _available = v);
    });
  }

  @override
  void dispose() {
    _pulse.dispose();
    if (_listening) Speech.instance.stopListening();
    super.dispose();
  }

  Future<void> _record() async {
    if (_listening) {
      await Speech.instance.stopListening();
      return;
    }
    setState(() {
      _listening = true;
      _heard = null;
      _hits = null;
      _status = 'Eshityapman... gapiring, tugatgach biroz jim turing';
    });
    _pulse.repeat();
    // Words turn green live, as the recognizer hears them.
    final heard = await Speech.instance.listen(
      onPartial: (text) {
        if (mounted) {
          setState(() {
            _heard = text;
            _hits = speechScore(_text, [text]).hits;
          });
        }
      },
    );
    if (!mounted) return;
    _pulse.stop();
    setState(() => _listening = false);
    if (!heard.ok) {
      setState(() => _status = heard.error);
      return;
    }
    final alts = heard.alternatives;
    final r = speechScore(_text, alts);
    _tries++;
    setState(() {
      _hits = r.hits;
      _heard = alts.first;
    });
    final pct = (r.score * 100).round();
    if (r.score >= 0.65) {
      widget.ctl.resolve(Outcome(ok: true, title: 'Ajoyib talaffuz! $pct%'));
    } else if (_tries >= 3) {
      widget.ctl.resolve(
        Outcome(
          ok: true,
          graded: false,
          title: "$pct% — mashq qilishda davom eting",
          note: "Qizil so'zlarni tinglab takrorlang.",
        ),
      );
    } else {
      setState(() => _status = "$pct% — yana bir bor urinib ko'ring. Qizil so'zlarni aniqroq ayting.");
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final words = _text.split(RegExp(r'\s+'));
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Kicker(Icons.mic_rounded, 'Gapirish'),
        StepTitle('${widget.step['uz'] ?? 'Ovoz chiqarib ayting'}'),
        const SizedBox(height: 8),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Row(
              children: [
                Expanded(
                  child: Wrap(
                    spacing: 6,
                    runSpacing: 4,
                    children: [
                      for (var i = 0; i < words.length; i++)
                        Text(
                          words[i],
                          style: TextStyle(
                            fontSize: 21,
                            fontWeight: FontWeight.w700,
                            color: _hits == null || i >= _hits!.length ? null : (_hits![i] ? Brand.ok : Brand.bad),
                          ),
                        ),
                    ],
                  ),
                ),
                SayButton(_text),
              ],
            ),
          ),
        ),
        const SizedBox(height: 28),
        if (_available == false)
          Text(
            "Telefoningizda ovozni tanish xizmati topilmadi. Gapni tinglang va ovoz chiqarib 2–3 marta takrorlang, keyin \"O'tkazish\"ni bosing.",
            textAlign: TextAlign.center,
            style: TextStyle(color: scheme.outline),
          )
        else ...[
          Center(
            child: SizedBox(
              width: 160,
              height: 160,
              child: Stack(
                alignment: Alignment.center,
                children: [
                  if (_listening)
                    AnimatedBuilder(
                      animation: _pulse,
                      builder: (_, _) => Container(
                        width: 108 + 52 * _pulse.value,
                        height: 108 + 52 * _pulse.value,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: Brand.bad.withValues(alpha: 0.25 * (1 - _pulse.value)),
                        ),
                      ),
                    ),
                  GestureDetector(
                    onTap: widget.ctl.answered ? null : _record,
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 300),
                      width: _listening ? 108 : 92,
                      height: _listening ? 108 : 92,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        gradient: _listening ? null : Brand.heroGradient,
                        color: _listening ? Brand.bad : null,
                        boxShadow: [
                          BoxShadow(
                            color: (_listening ? Brand.bad : Brand.primary).withValues(alpha: 0.4),
                            blurRadius: _listening ? 28 : 14,
                          ),
                        ],
                      ),
                      child: Icon(_listening ? Icons.stop_rounded : Icons.mic_rounded, color: Colors.white, size: 44),
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 4),
          Text(
            _status ?? 'Avval namunani tinglang, keyin mikrofonni bosib ayting',
            textAlign: TextAlign.center,
            style: TextStyle(color: scheme.outline),
          ),
          if (_heard != null) ...[
            const SizedBox(height: 8),
            Text(
              'Siz: "$_heard"',
              textAlign: TextAlign.center,
              style: const TextStyle(fontStyle: FontStyle.italic),
            ),
          ],
        ],
      ],
    );
  }
}

// ── write (AI feedback) ──────────────────────────────────────────────────
class WriteStep extends StatefulWidget {
  const WriteStep({super.key, required this.step, required this.ctl, required this.env});

  final Map<String, dynamic> step;
  final StepCtl ctl;
  final StepEnv env;

  @override
  State<WriteStep> createState() => _WriteStepState();
}

class _WriteStepState extends State<WriteStep> {
  final _input = TextEditingController();
  bool _model = false;
  Map<String, dynamic>? _ai;

  int get _words => _input.text.trim().isEmpty ? 0 : _input.text.trim().split(RegExp(r'\s+')).length;

  @override
  void initState() {
    super.initState();
    _input.addListener(() {
      widget.ctl.setReady(_words >= 3);
      setState(() {});
    });
    widget.ctl.configure(skippable: true, check: _check);
  }

  Future<Outcome?> _check() async {
    try {
      final r = await widget.env.api.post('write-check/', {
        'slug': widget.env.slug,
        'step': widget.env.stepIndex,
        'text': _input.text,
      });
      setState(() => _ai = r);
      return const Outcome(ok: true, graded: false, title: "AI izohini o'qing");
    } on ApiException catch (e) {
      // Without AI the task still has value: compare with the model yourself.
      setState(() => _model = true);
      return Outcome(ok: true, graded: false, title: 'Matningizni namuna bilan solishtiring', note: e.message);
    }
  }

  @override
  void dispose() {
    _input.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.step;
    final scheme = Theme.of(context).colorScheme;
    final min = s['min_words'];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Kicker(Icons.draw_rounded, 'Yozish'),
        StepTitle('${s['prompt_uz'] ?? ''}'),
        if (s['prompt'] != null) StepSub('${s['prompt']}'),
        if (s['example'] != null)
          OutlinedButton.icon(
            onPressed: () => setState(() => _model = !_model),
            icon: Icon(_model ? Icons.visibility_off_rounded : Icons.visibility_rounded),
            label: Text(_model ? 'Namunani yashirish' : "Namunani ko'rish"),
          ),
        if (_model && s['example'] != null)
          Container(
            margin: const EdgeInsets.only(top: 10),
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: scheme.primary.withValues(alpha: 0.07),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Text('${s['example']}', style: const TextStyle(height: 1.5)),
          ),
        const SizedBox(height: 12),
        TextField(
          controller: _input,
          enabled: !widget.ctl.answered,
          minLines: 6,
          maxLines: 14,
          textCapitalization: TextCapitalization.sentences,
          decoration: const InputDecoration(hintText: "Inglizcha yozing... Xato qilishdan qo'rqmang!"),
        ),
        Padding(
          padding: const EdgeInsets.only(top: 6),
          child: Text(
            "$_words so'z${min != null ? ' · tavsiya: $min+' : ''}",
            style: TextStyle(color: scheme.outline, fontSize: 13),
          ),
        ),
        if (_ai != null) _AiFeedback(data: _ai!),
      ],
    );
  }
}

class _AiFeedback extends StatelessWidget {
  const _AiFeedback({required this.data});

  final Map<String, dynamic> data;

  @override
  Widget build(BuildContext context) {
    final score = (data['score'] as int?) ?? 0;
    final color = score >= 70
        ? Brand.ok
        : score >= 40
        ? Brand.warn
        : Brand.bad;
    final mistakes = ((data['mistakes'] as List?) ?? []).cast<Map>();
    final scheme = Theme.of(context).colorScheme;
    Widget h(String t) => Padding(
      padding: const EdgeInsets.only(top: 14, bottom: 6),
      child: Text(t, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
    );
    return Card(
      margin: const EdgeInsets.only(top: 16),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(
                  '$score',
                  style: TextStyle(fontSize: 34, fontWeight: FontWeight.w900, color: color),
                ),
                Text(' / 100', style: TextStyle(color: scheme.outline)),
                const Spacer(),
                const Pill(label: 'AI tekshiruv', icon: Icons.auto_awesome_rounded),
              ],
            ),
            if ('${data['praise_uz'] ?? ''}'.isNotEmpty) Text('👍 ${data['praise_uz']}'),
            if (mistakes.isNotEmpty) ...[
              h('Xatolar'),
              for (final m in mistakes)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Text.rich(
                    TextSpan(
                      children: [
                        TextSpan(
                          text: '${m['wrong']}',
                          style: const TextStyle(decoration: TextDecoration.lineThrough, color: Brand.bad),
                        ),
                        const TextSpan(text: '  →  '),
                        TextSpan(
                          text: '${m['right']}',
                          style: const TextStyle(color: Brand.ok, fontWeight: FontWeight.w700),
                        ),
                        TextSpan(
                          text: '\n${m['why_uz'] ?? ''}',
                          style: TextStyle(color: scheme.outline, fontSize: 13),
                        ),
                      ],
                    ),
                  ),
                ),
            ] else
              const Padding(
                padding: EdgeInsets.only(top: 8),
                child: Text('Jiddiy xato topilmadi!', style: TextStyle(color: Brand.ok)),
              ),
            if ('${data['corrected'] ?? ''}'.isNotEmpty) ...[
              h('Tuzatilgan matn'),
              Text('${data['corrected']}', style: const TextStyle(height: 1.5)),
            ],
            if ('${data['next_uz'] ?? ''}'.isNotEmpty) ...[h('Keyingi qadam'), Text('${data['next_uz']}')],
          ],
        ),
      ),
    );
  }
}
