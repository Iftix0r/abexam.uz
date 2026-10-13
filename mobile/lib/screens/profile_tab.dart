import 'package:flutter/material.dart';

import '../core/app_state.dart';
import '../core/sfx.dart';
import '../core/speech.dart';
import '../core/theme.dart';
import '../widgets/common.dart';
import 'grammar_screen.dart';
import 'placement_screen.dart';

class ProfileTab extends StatelessWidget {
  const ProfileTab({super.key});

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    final me = state.me ?? {};
    final scheme = Theme.of(context).colorScheme;
    final review = (me['review'] as Map?) ?? {};
    final goals = ((me['daily_goals'] as List?) ?? [10, 20, 30, 50]).cast<int>();
    final user = (me['user'] as Map?) ?? {};
    final name = '${user['first_name'] ?? ''} ${user['last_name'] ?? ''}'.trim();

    return SafeArea(
      child: RefreshIndicator(
        onRefresh: state.refresh,
        child: ListView(padding: const EdgeInsets.all(16), children: [
          Row(children: [
            CircleAvatar(
              radius: 34,
              backgroundColor: Brand.level(state.levelCode),
              child: Text(state.displayName.isEmpty ? '?' : state.displayName[0].toUpperCase(),
                  style: const TextStyle(fontSize: 28, color: Colors.white, fontWeight: FontWeight.w900)),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(name.isEmpty ? '${user['username'] ?? ''}' : name, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w900)),
                Text('@${user['username'] ?? ''}', style: TextStyle(color: scheme.outline)),
                const SizedBox(height: 4),
                Pill(label: 'Daraja: ${state.levelCode}', color: Brand.level(state.levelCode)),
              ]),
            ),
          ]),
          const SizedBox(height: 20),
          GridView.count(
            crossAxisCount: 2,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            mainAxisSpacing: 10,
            crossAxisSpacing: 10,
            childAspectRatio: 2.1,
            children: [
              _stat(context, Icons.bolt_rounded, Brand.warn, '${me['xp'] ?? 0}', 'Jami XP'),
              _stat(context, Icons.local_fire_department_rounded, Brand.flame, '${me['streak'] ?? 0}', 'Kunlik seriya'),
              _stat(context, Icons.emoji_events_rounded, Brand.violet, '${me['best_streak'] ?? 0}', 'Eng uzun seriya'),
              _stat(context, Icons.style_rounded, Brand.ok, '${review['learned'] ?? 0}', "O'rganilgan so'z"),
            ],
          ),
          const SectionTitle('Kunlik maqsad'),
          Wrap(spacing: 8, children: [
            for (final g in goals)
              ChoiceChip(
                label: Text('$g XP'),
                selected: me['daily_goal'] == g,
                onSelected: (_) => state.updateProfile(dailyGoal: g).catchError((e) {
                  if (context.mounted) showError(context, e);
                }),
              ),
          ]),
          const SectionTitle('Eslatma'),
          Card(
            child: Column(children: [
              SwitchListTile(
                secondary: const Icon(Icons.notifications_active_rounded),
                title: const Text('Kunlik eslatma'),
                subtitle: const Text("Maqsad bajarilgan kuni eslatmaydi"),
                value: state.reminderOn,
                onChanged: (v) => state.setReminder(on: v),
              ),
              ListTile(
                enabled: state.reminderOn,
                leading: const Icon(Icons.schedule_rounded),
                title: const Text('Vaqti'),
                trailing: Text(
                  '${(state.reminderMinutes ~/ 60).toString().padLeft(2, '0')}:${(state.reminderMinutes % 60).toString().padLeft(2, '0')}',
                  style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16, color: scheme.primary),
                ),
                onTap: () async {
                  final t = await showTimePicker(
                    context: context,
                    initialTime: TimeOfDay(hour: state.reminderMinutes ~/ 60, minute: state.reminderMinutes % 60),
                    helpText: 'Eslatma vaqti',
                    builder: (c, child) => MediaQuery(data: MediaQuery.of(c).copyWith(alwaysUse24HourFormat: true), child: child!),
                  );
                  if (t != null) state.setReminder(minutes: t.hour * 60 + t.minute);
                },
              ),
            ]),
          ),
          const SectionTitle('Sozlamalar'),
          Card(
            child: Column(children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 14, 16, 6),
                child: Row(children: [
                  const Icon(Icons.palette_outlined),
                  const SizedBox(width: 16),
                  const Expanded(child: Text('Mavzu', style: TextStyle(fontSize: 16))),
                  SegmentedButton<ThemeMode>(
                    showSelectedIcon: false,
                    style: SegmentedButton.styleFrom(visualDensity: VisualDensity.compact),
                    segments: const [
                      ButtonSegment(value: ThemeMode.system, icon: Icon(Icons.brightness_auto_rounded), tooltip: 'Tizim'),
                      ButtonSegment(value: ThemeMode.light, icon: Icon(Icons.light_mode_rounded), tooltip: "Yorug'"),
                      ButtonSegment(value: ThemeMode.dark, icon: Icon(Icons.dark_mode_rounded), tooltip: "Qorong'i"),
                    ],
                    selected: {state.themeMode},
                    onSelectionChanged: (s) => state.setThemeMode(s.first),
                  ),
                ]),
              ),
              SwitchListTile(
                secondary: const Icon(Icons.speed_rounded),
                title: const Text('Sekin talaffuz'),
                subtitle: const Text('Audio sekinroq o\'qiladi'),
                value: state.slowSpeech,
                onChanged: (v) {
                  Speech.instance.slow = v;
                  state.setSlowSpeech(v);
                },
              ),
              SwitchListTile(
                secondary: const Icon(Icons.music_note_rounded),
                title: const Text('Ovoz effektlari'),
                subtitle: const Text("To'g'ri / xato javob tovushi"),
                value: state.sounds,
                onChanged: (v) {
                  Sfx.enabled = v;
                  state.setSounds(v);
                },
              ),
              SwitchListTile(
                secondary: const Icon(Icons.vibration_rounded),
                title: const Text('Tebranish'),
                subtitle: const Text("To'g'ri / xato javobda"),
                value: state.haptics,
                onChanged: state.setHaptics,
              ),
            ]),
          ),
          const SizedBox(height: 12),
          Card(
            child: Column(children: [
              ListTile(
                leading: const Icon(Icons.leaderboard_rounded, color: Brand.warn),
                title: const Text('Haftalik reyting'),
                trailing: const Icon(Icons.chevron_right_rounded),
                onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const LeaderboardScreen())),
              ),
              ListTile(
                leading: const Icon(Icons.menu_book_rounded, color: Brand.violet),
                title: const Text("Grammatika ma'lumotnomasi"),
                trailing: const Icon(Icons.chevron_right_rounded),
                onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const GrammarScreen())),
              ),
              ListTile(
                leading: const Icon(Icons.quiz_rounded, color: Brand.primary),
                title: const Text('Darajani qayta aniqlash'),
                trailing: const Icon(Icons.chevron_right_rounded),
                onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const PlacementScreen())),
              ),
            ]),
          ),
          const SizedBox(height: 20),
          OutlinedButton.icon(
            style: OutlinedButton.styleFrom(foregroundColor: Brand.bad),
            onPressed: () async {
              final ok = await showDialog<bool>(
                context: context,
                builder: (c) => AlertDialog(
                  title: const Text('Chiqish'),
                  content: const Text('Hisobdan chiqasizmi?'),
                  actions: [
                    TextButton(onPressed: () => Navigator.pop(c, false), child: const Text("Yo'q")),
                    TextButton(onPressed: () => Navigator.pop(c, true), child: const Text('Chiqish')),
                  ],
                ),
              );
              if (ok == true) state.signOut();
            },
            icon: const Icon(Icons.logout_rounded),
            label: const Text('Hisobdan chiqish'),
          ),
        ]),
      ),
    );
  }

  Widget _stat(BuildContext context, IconData icon, Color color, String value, String label) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14),
        child: Row(children: [
          Icon(icon, color: color, size: 30),
          const SizedBox(width: 10),
          Expanded(
            child: Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(value, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w900)),
              Text(label, style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.outline), overflow: TextOverflow.ellipsis),
            ]),
          ),
        ]),
      ),
    );
  }
}

class LeaderboardScreen extends StatelessWidget {
  const LeaderboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final api = AppScope.read(context).api;
    return Scaffold(
      appBar: AppBar(title: const Text('Haftalik reyting')),
      body: Loader<Map<String, dynamic>>(
        load: () => api.get('leaderboard/'),
        builder: (context, data, reload) {
          final rows = (data['rows'] as List).cast<Map<String, dynamic>>();
          final me = data['me'] as Map?;
          return RefreshIndicator(
            onRefresh: reload,
            child: ListView(padding: const EdgeInsets.all(16), children: [
              Container(
                padding: const EdgeInsets.all(18),
                decoration: BoxDecoration(gradient: Brand.heroGradient, borderRadius: BorderRadius.circular(20)),
                child: Row(children: [
                  const Text('🏆', style: TextStyle(fontSize: 40)),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Text(
                      me == null ? "Bu hafta hali XP yig'madingiz. Bitta dars — va siz reytingdasiz!" : 'Siz ${me['rank']}-o\'rindasiz · ${me['xp']} XP',
                      style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 16),
                    ),
                  ),
                ]),
              ),
              const SizedBox(height: 14),
              for (final r in rows)
                Card(
                  color: r['me'] == true ? Brand.primary.withValues(alpha: 0.12) : null,
                  margin: const EdgeInsets.only(bottom: 8),
                  child: ListTile(
                    leading: CircleAvatar(
                      backgroundColor: switch (r['rank']) {
                        1 => const Color(0xFFFACC15),
                        2 => const Color(0xFFCBD5E1),
                        3 => const Color(0xFFF59E0B),
                        _ => Theme.of(context).colorScheme.surfaceContainerHighest,
                      },
                      child: Text('${r['rank']}', style: const TextStyle(fontWeight: FontWeight.w900, color: Colors.black87)),
                    ),
                    title: Text('${r['name']}', style: TextStyle(fontWeight: r['me'] == true ? FontWeight.w900 : FontWeight.w600)),
                    trailing: Text('${r['xp']} XP', style: const TextStyle(fontWeight: FontWeight.w800)),
                  ),
                ),
            ]),
          );
        },
      ),
    );
  }
}
