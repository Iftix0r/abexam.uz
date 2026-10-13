import 'dart:math';

import 'package:flutter/material.dart';

import '../core/app_state.dart';
import '../core/theme.dart';
import '../widgets/common.dart';
import 'grammar_screen.dart';
import 'lesson/lesson_screen.dart';
import 'placement_screen.dart';

class LearnTab extends StatefulWidget {
  const LearnTab({super.key, required this.onOpenReview});

  final VoidCallback onOpenReview;

  @override
  State<LearnTab> createState() => LearnTabState();
}

class LearnTabState extends State<LearnTab> {
  String? _level;
  Map<String, dynamic>? _course;
  Object? _error;

  @override
  void initState() {
    super.initState();
    reload();
  }

  Future<void> reload() async {
    final state = AppScope.read(context);
    try {
      final course = await state.api.get('course/', query: {'level': ?_level});
      if (!mounted) return;
      setState(() {
        _course = course;
        _level = course['level'] as String;
        _error = null;
      });
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  Future<void> _pickLevel(String code) async {
    setState(() => _level = code);
    final state = AppScope.read(context);
    try {
      await state.updateProfile(level: code);
    } catch (_) {}
    await reload();
  }

  Future<void> _open(Widget screen) async {
    await Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen));
    if (!mounted) return;
    AppScope.read(context).refresh().catchError((_) {});
    reload();
  }

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    if (_course == null) {
      return SafeArea(
        child: _error != null ? ErrorView(error: _error!, onRetry: reload) : const Center(child: CircularProgressIndicator()),
      );
    }
    final course = _course!;
    final units = (course['units'] as List).cast<Map<String, dynamic>>();
    final me = state.me ?? {};
    final current = course['current'] as String?;
    Map<String, dynamic>? currentLesson;
    for (final u in units) {
      for (final l in (u['lessons'] as List).cast<Map<String, dynamic>>()) {
        if (l['slug'] == current) currentLesson = l;
      }
    }

    return RefreshIndicator(
      onRefresh: () async {
        await Future.wait([reload(), state.refresh().catchError((_) {})]);
      },
      child: CustomScrollView(slivers: [
        SliverSafeArea(
          bottom: false,
          sliver: SliverPadding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
            sliver: SliverList.list(children: [
              _Header(me: me, name: state.displayName),
              const SizedBox(height: 16),
              _GoalCard(me: me),
              if (me['show_placement'] == true) ...[
                const SizedBox(height: 14),
                _ActionCard(
                  icon: Icons.quiz_rounded,
                  color: Brand.warn,
                  title: 'Darajangizni aniqlang',
                  subtitle: "5 daqiqalik test — qaysi darajadan boshlashni ko'rsatadi",
                  onTap: () => _open(const PlacementScreen()),
                ),
              ],
              const SizedBox(height: 18),
              _LevelPicker(levels: (course['levels'] as List).cast<Map<String, dynamic>>(), selected: _level!, onPick: _pickLevel),
              if (currentLesson != null) ...[
                const SizedBox(height: 16),
                _ContinueCard(lesson: currentLesson, onTap: () => _open(LessonScreen.lesson(currentLesson!['slug'] as String))),
              ],
              const SizedBox(height: 14),
              Row(children: [
                Expanded(
                  child: _MiniAction(
                    icon: Icons.replay_circle_filled_rounded,
                    color: Brand.flame,
                    title: 'Xatolar',
                    value: '${me['mistakes'] ?? 0}',
                    onTap: () => _open(LessonScreen.practice()),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: _MiniAction(
                    icon: Icons.style_rounded,
                    color: Brand.levels['B1']!,
                    title: "So'zlar",
                    value: '${(me['review'] as Map?)?['session'] ?? 0}',
                    onTap: widget.onOpenReview,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: _MiniAction(
                    icon: Icons.menu_book_rounded,
                    color: Brand.violet,
                    title: 'Grammatika',
                    value: '📖',
                    onTap: () => _open(const GrammarScreen()),
                  ),
                ),
              ]),
            ]),
          ),
        ),
        SliverPadding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
          sliver: SliverList.builder(
            itemCount: units.length,
            itemBuilder: (context, i) => _UnitPath(
              unit: units[i],
              index: i,
              level: _level!,
              onOpen: (slug) => _open(LessonScreen.lesson(slug)),
            ),
          ),
        ),
      ]),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.me, required this.name});

  final Map<String, dynamic> me;
  final String name;

  @override
  Widget build(BuildContext context) {
    return Row(children: [
      Expanded(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(name.isEmpty ? 'Salom! 👋' : 'Salom, $name! 👋',
              style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w900), overflow: TextOverflow.ellipsis),
          const SizedBox(height: 2),
          Text("Bugun ham bir qadam oldinga", style: TextStyle(color: Theme.of(context).colorScheme.outline)),
        ]),
      ),
      Pill(label: '${me['streak'] ?? 0}', icon: Icons.local_fire_department_rounded, color: Brand.flame),
      const SizedBox(width: 8),
      Pill(label: '${me['xp'] ?? 0} XP', icon: Icons.bolt_rounded, color: Brand.warn),
    ]);
  }
}

class _GoalCard extends StatelessWidget {
  const _GoalCard({required this.me});

  final Map<String, dynamic> me;

  @override
  Widget build(BuildContext context) {
    final today = (me['xp_today'] as int?) ?? 0;
    final goal = max(1, (me['daily_goal'] as int?) ?? 30);
    final pct = min(1.0, today / goal);
    final week = ((me['week'] as List?) ?? []).cast<Map>();
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        gradient: Brand.heroGradient,
        borderRadius: BorderRadius.circular(22),
        boxShadow: [BoxShadow(color: Brand.primary.withValues(alpha: 0.35), blurRadius: 18, offset: const Offset(0, 8))],
      ),
      child: Row(children: [
        SizedBox(
          width: 82,
          height: 82,
          child: Stack(alignment: Alignment.center, children: [
            SizedBox.expand(
              child: TweenAnimationBuilder<double>(
                tween: Tween(begin: 0, end: pct),
                duration: const Duration(milliseconds: 900),
                curve: Curves.easeOutCubic,
                builder: (_, v, _) => CircularProgressIndicator(
                  value: v,
                  strokeWidth: 9,
                  strokeCap: StrokeCap.round,
                  backgroundColor: Colors.white24,
                  color: Colors.white,
                ),
              ),
            ),
            Column(mainAxisSize: MainAxisSize.min, children: [
              Text('$today', style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w900)),
              Text('/ $goal XP', style: const TextStyle(color: Colors.white70, fontSize: 11)),
            ]),
          ]),
        ),
        const SizedBox(width: 18),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(pct >= 1 ? 'Kunlik maqsad bajarildi! 🎉' : 'Kunlik maqsad',
                style: const TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w800)),
            const SizedBox(height: 10),
            SizedBox(
              height: 46,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  for (final d in week)
                    Expanded(
                      child: Column(mainAxisAlignment: MainAxisAlignment.end, children: [
                        Container(
                          height: 4 + 26 * min(1.0, ((d['xp'] as int?) ?? 0) / goal),
                          margin: const EdgeInsets.symmetric(horizontal: 3),
                          decoration: BoxDecoration(
                            color: d['today'] == true ? Colors.white : Colors.white54,
                            borderRadius: BorderRadius.circular(4),
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text('${d['label']}', style: const TextStyle(color: Colors.white70, fontSize: 10)),
                      ]),
                    ),
                ],
              ),
            ),
          ]),
        ),
      ]),
    );
  }
}

class _LevelPicker extends StatelessWidget {
  const _LevelPicker({required this.levels, required this.selected, required this.onPick});

  final List<Map<String, dynamic>> levels;
  final String selected;
  final ValueChanged<String> onPick;

  @override
  Widget build(BuildContext context) {
    final info = levels.firstWhere((l) => l['code'] == selected, orElse: () => levels.first);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      SizedBox(
        height: 64,
        child: ListView.separated(
          scrollDirection: Axis.horizontal,
          itemCount: levels.length,
          separatorBuilder: (_, _) => const SizedBox(width: 8),
          itemBuilder: (context, i) {
            final l = levels[i];
            final code = l['code'] as String;
            final on = code == selected;
            final color = Brand.level(code);
            final total = max(1, (l['total'] as int?) ?? 1);
            return GestureDetector(
              onTap: () => onPick(code),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 250),
                width: 72,
                padding: const EdgeInsets.symmetric(vertical: 8),
                decoration: BoxDecoration(
                  color: on ? color : Theme.of(context).cardTheme.color,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: on ? color : color.withValues(alpha: 0.3), width: 1.5),
                ),
                child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                  Text(code, style: TextStyle(fontSize: 18, fontWeight: FontWeight.w900, color: on ? Colors.white : color)),
                  const SizedBox(height: 4),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(4),
                      child: LinearProgressIndicator(
                        value: ((l['done'] as int?) ?? 0) / total,
                        minHeight: 4,
                        backgroundColor: (on ? Colors.white : color).withValues(alpha: 0.2),
                        color: on ? Colors.white : color,
                      ),
                    ),
                  ),
                ]),
              ),
            );
          },
        ),
      ),
      const SizedBox(height: 10),
      Text('${info['name']} · IELTS ${info['ielts']}',
          style: TextStyle(fontWeight: FontWeight.w800, color: Brand.level(selected))),
      const SizedBox(height: 2),
      Text('${info['desc']}', style: TextStyle(color: Theme.of(context).colorScheme.outline, fontSize: 13)),
    ]);
  }
}

class _ContinueCard extends StatelessWidget {
  const _ContinueCard({required this.lesson, required this.onTap});

  final Map<String, dynamic> lesson;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(children: [
            Container(
              width: 54,
              height: 54,
              decoration: BoxDecoration(gradient: Brand.heroGradient, borderRadius: BorderRadius.circular(16)),
              child: const Icon(Icons.play_arrow_rounded, color: Colors.white, size: 34),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('DAVOM ETISH', style: TextStyle(fontSize: 11, letterSpacing: 1.2, fontWeight: FontWeight.w800, color: Theme.of(context).colorScheme.primary)),
                const SizedBox(height: 3),
                Text('${lesson['title']}', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800), maxLines: 1, overflow: TextOverflow.ellipsis),
                Text('${lesson['title_uz']} · ${lesson['minutes']} daq',
                    style: TextStyle(color: Theme.of(context).colorScheme.outline, fontSize: 13), maxLines: 1, overflow: TextOverflow.ellipsis),
              ]),
            ),
            const Icon(Icons.chevron_right_rounded),
          ]),
        ),
      ),
    );
  }
}

class _MiniAction extends StatelessWidget {
  const _MiniAction({required this.icon, required this.color, required this.title, required this.value, required this.onTap});

  final IconData icon;
  final Color color;
  final String title;
  final String value;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 10),
          child: Column(children: [
            Icon(icon, color: color, size: 28),
            const SizedBox(height: 6),
            Text(value, style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 16)),
            Text(title, style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.outline)),
          ]),
        ),
      ),
    );
  }
}

class _ActionCard extends StatelessWidget {
  const _ActionCard({required this.icon, required this.color, required this.title, required this.subtitle, required this.onTap});

  final IconData icon;
  final Color color;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: color.withValues(alpha: 0.12),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
        leading: CircleAvatar(backgroundColor: color, child: Icon(icon, color: Colors.white)),
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
        subtitle: Text(subtitle),
        trailing: const Icon(Icons.chevron_right_rounded),
        onTap: onTap,
      ),
    );
  }
}

/// One unit as a winding path of lesson nodes.
class _UnitPath extends StatelessWidget {
  const _UnitPath({required this.unit, required this.index, required this.level, required this.onOpen});

  final Map<String, dynamic> unit;
  final int index;
  final String level;
  final ValueChanged<String> onOpen;

  @override
  Widget build(BuildContext context) {
    final lessons = (unit['lessons'] as List).cast<Map<String, dynamic>>();
    final done = lessons.where((l) => l['state'] == 'done').length;
    final color = Brand.level(level);
    return Padding(
      padding: const EdgeInsets.only(top: 20),
      child: Column(children: [
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: color.withValues(alpha: 0.1),
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: color.withValues(alpha: 0.25)),
          ),
          child: Row(children: [
            CircleAvatar(radius: 22, backgroundColor: color, child: Icon(unitIcon(unit['icon'] as String), color: Colors.white)),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('$level · ${index + 1}-BO\'LIM', style: TextStyle(fontSize: 11, letterSpacing: 1, fontWeight: FontWeight.w800, color: color)),
                Text('${unit['title_uz']}', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
              ]),
            ),
            Text('$done/${lessons.length}', style: TextStyle(fontWeight: FontWeight.w800, color: color)),
          ]),
        ),
        const SizedBox(height: 8),
        for (var i = 0; i < lessons.length; i++)
          _LessonNode(lesson: lessons[i], offset: [0.0, 0.55, -0.55][i % 3], color: color, onOpen: onOpen),
      ]),
    );
  }
}

class _LessonNode extends StatelessWidget {
  const _LessonNode({required this.lesson, required this.offset, required this.color, required this.onOpen});

  final Map<String, dynamic> lesson;
  final double offset;
  final Color color;
  final ValueChanged<String> onOpen;

  @override
  Widget build(BuildContext context) {
    final state = lesson['state'] as String;
    final locked = state == 'locked';
    final current = state == 'current';
    final doneState = state == 'done';
    final scheme = Theme.of(context).colorScheme;
    final bg = locked ? scheme.surfaceContainerHighest : color;
    final icon = doneState
        ? Icons.check_rounded
        : locked
            ? Icons.lock_rounded
            : Icons.star_rounded;

    final node = GestureDetector(
      onTap: () {
        if (locked) {
          ScaffoldMessenger.of(context)
            ..hideCurrentSnackBar()
            ..showSnackBar(const SnackBar(content: Text('Avval oldingi darsni tugating 🔒')));
        } else {
          onOpen(lesson['slug'] as String);
        }
      },
      child: Column(children: [
        Stack(alignment: Alignment.center, children: [
          if (current)
            Container(
              width: 92,
              height: 92,
              decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: color.withValues(alpha: 0.35), width: 6)),
            ),
          Container(
            width: 72,
            height: 72,
            decoration: BoxDecoration(
              color: bg,
              shape: BoxShape.circle,
              boxShadow: [
                BoxShadow(color: (locked ? Colors.black : color).withValues(alpha: locked ? 0.08 : 0.4), offset: const Offset(0, 6), blurRadius: 0),
              ],
            ),
            child: Icon(icon, color: locked ? scheme.outline : Colors.white, size: 34),
          ),
        ]),
        const SizedBox(height: 6),
        SizedBox(
          width: 170,
          child: Text(
            '${lesson['title']}',
            textAlign: TextAlign.center,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(fontWeight: FontWeight.w700, fontSize: 13, color: locked ? scheme.outline : null),
          ),
        ),
        if (doneState && lesson['score'] != null)
          Text('${lesson['score']}%', style: TextStyle(fontSize: 12, color: color, fontWeight: FontWeight.w800)),
      ]),
    );
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Align(alignment: Alignment(offset, 0), child: node),
    );
  }
}
