import 'dart:math';

import 'package:flutter/material.dart';

/// Answer checking — mirrors learn/content.py and templates/learn/lesson.html
/// so an answer accepted on the website is accepted in the app.
String norm(String? s) {
  var t = (s ?? '').toLowerCase().replaceAll('’', "'").replaceAll('‘', "'");
  t = t.replaceAll(RegExp(r"[^\p{L}\p{N}\s']", unicode: true), ' ');
  return t.split(RegExp(r'\s+')).where((w) => w.isNotEmpty).join(' ');
}

List<String> answersOf(dynamic answer) =>
    answer is List ? answer.map((e) => e.toString()).toList() : [if (answer != null) answer.toString()];

int levenshtein(String a, String b) {
  final d = List<int>.generate(b.length + 1, (j) => j);
  for (var i = 1; i <= a.length; i++) {
    var prev = d[0];
    d[0] = i;
    for (var j = 1; j <= b.length; j++) {
      final tmp = d[j];
      d[j] = min(min(d[j] + 1, d[j - 1] + 1), prev + (a[i - 1] == b[j - 1] ? 0 : 1));
      prev = tmp;
    }
  }
  return d[b.length];
}

String _stem(String w) => w.replaceFirst(RegExp(r"(es|s|ed|d|'s)$"), '');

class Grade {
  const Grade(this.ok, [this.typo]);

  final bool ok;

  /// The accepted spelling when the learner made a small slip.
  final String? typo;
}

/// Exact match, or a small spelling slip that isn't the grammar point itself:
/// "Samarqand" for "Samarkand" passes as a typo, "drink" for "drinks" does not.
Grade grade(String given, dynamic accepted) {
  final g = norm(given);
  final list = answersOf(accepted);
  if (g.isEmpty) return const Grade(false);
  if (list.any((a) => norm(a) == g)) return const Grade(true);
  final gw = g.split(' ');
  for (final a in list) {
    final aw = norm(a).split(' ');
    if (aw.length != gw.length) continue;
    var slips = 0, apos = 0;
    var fine = true;
    for (var i = 0; i < aw.length && fine; i++) {
      if (aw[i] == gw[i]) continue;
      if (aw[i].replaceAll("'", '') == gw[i].replaceAll("'", '')) {
        apos++;
        continue;
      }
      final hasApos = aw[i].contains("'") || gw[i].contains("'");
      if (aw[i].length >= 4 && levenshtein(aw[i], gw[i]) == 1 && _stem(aw[i]) != _stem(gw[i]) && !hasApos) {
        slips++;
      } else {
        fine = false;
      }
    }
    if (fine && (slips > 0 || apos > 0) && slips <= max(1, aw.length ~/ 4)) return Grade(true, a);
  }
  return const Grade(false);
}

/// Pronunciation score: share of target words heard (one sound off is fine).
({double score, List<bool> hits}) speechScore(String target, List<String> heardAlternatives) {
  final want = norm(target).split(' ');
  var best = (score: -1.0, hits: <bool>[]);
  for (final alt in heardAlternatives) {
    final got = norm(alt.replaceAll('-', ' ')).split(' ');
    final hits = want.map((w) => got.any((g) => g == w || (w.length > 3 && levenshtein(g, w) <= 1))).toList();
    final score = want.isEmpty ? 0.0 : hits.where((h) => h).length / want.length;
    if (score > best.score) best = (score: score, hits: hits);
  }
  return best.score < 0 ? (score: 0.0, hits: List.filled(want.length, false)) : best;
}

List<String> tokensOf(String s) =>
    s.replaceAll(RegExp(r'[.,!?;:]'), '').split(RegExp(r'\s+')).where((w) => w.isNotEmpty).toList();

final _rng = Random();

List<T> shuffled<T>(Iterable<T> items) => items.toList()..shuffle(_rng);

/// Renders the course's light markdown: **bold** and line breaks.
TextSpan md(String? text, TextStyle base, {Color? strongColor}) {
  final spans = <TextSpan>[];
  final re = RegExp(r'\*\*(.+?)\*\*');
  var last = 0;
  final s = text ?? '';
  for (final m in re.allMatches(s)) {
    if (m.start > last) spans.add(TextSpan(text: s.substring(last, m.start)));
    spans.add(TextSpan(text: m.group(1), style: TextStyle(fontWeight: FontWeight.w800, color: strongColor)));
    last = m.end;
  }
  if (last < s.length) spans.add(TextSpan(text: s.substring(last)));
  return TextSpan(style: base, children: spans);
}
