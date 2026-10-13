import 'package:flutter/material.dart';

import '../core/app_state.dart';
import '../core/theme.dart';
import '../widgets/common.dart';

/// Lucide icon names used by the server's badges and quests.
IconData gameIcon(String name) {
  const map = {
    'graduation-cap': Icons.school_rounded,
    'flame': Icons.local_fire_department_rounded,
    'star': Icons.star_rounded,
    'library': Icons.local_library_rounded,
    'book-open': Icons.auto_stories_rounded,
    'zap': Icons.bolt_rounded,
    'layers': Icons.style_rounded,
    'target': Icons.track_changes_rounded,
    'messages-square': Icons.forum_rounded,
  };
  return map[name] ?? Icons.emoji_events_rounded;
}

class AchievementsScreen extends StatelessWidget {
  const AchievementsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = AppScope.read(context);
    final me = state.me ?? {};
    return Scaffold(
      appBar: AppBar(title: const Text('Yutuqlar')),
      body: Loader<Map<String, dynamic>>(
        load: () => state.api.get('achievements/'),
        builder: (context, data, reload) {
          final badges = (data['badges'] as List).cast<Map<String, dynamic>>();
          final unlocked = badges.fold<int>(0, (n, b) => n + (b['tier'] as int));
          final total = badges.fold<int>(0, (n, b) => n + (b['tiers'] as int));
          return RefreshIndicator(
            onRefresh: reload,
            child: ListView(padding: const EdgeInsets.all(16), children: [
              Row(children: [
                _sum(context, '$unlocked / $total', 'daraja ochilgan', Brand.warn),
                const SizedBox(width: 10),
                _sum(context, '🔥 ${me['streak'] ?? 0}', 'seriya', Brand.flame),
                const SizedBox(width: 10),
                _sum(context, '❄️ ${me['streak_freezes'] ?? 0}', 'muzlatgich', const Color(0xFF0EA5E9)),
              ]),
              const SizedBox(height: 16),
              for (final b in badges) _BadgeTile(b: b),
              const SizedBox(height: 8),
              Card(
                color: const Color(0xFF0EA5E9).withValues(alpha: 0.08),
                child: const ListTile(
                  leading: Icon(Icons.ac_unit_rounded, color: Color(0xFF0EA5E9), size: 30),
                  title: Text('Seriya muzlatgichi', style: TextStyle(fontWeight: FontWeight.w800)),
                  subtitle: Text("Har 7 kunlik seriyada bittasi beriladi (ko'pi bilan 2 ta). Bir kun dars qilmasangiz, "
                      "avtomatik ishlatiladi va seriya uzilmaydi."),
                ),
              ),
            ]),
          );
        },
      ),
    );
  }

  Widget _sum(BuildContext context, String value, String label, Color color) => Expanded(
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 14),
          decoration: BoxDecoration(color: color.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(16)),
          child: Column(children: [
            Text(value, style: TextStyle(fontSize: 18, fontWeight: FontWeight.w900, color: color)),
            Text(label, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
          ]),
        ),
      );
}

class _BadgeTile extends StatelessWidget {
  const _BadgeTile({required this.b});

  final Map<String, dynamic> b;

  @override
  Widget build(BuildContext context) {
    final tier = b['tier'] as int;
    final tiers = b['tiers'] as int;
    final next = b['next'];
    final gold = tier >= 3;
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(children: [
            Stack(clipBehavior: Clip.none, alignment: Alignment.bottomCenter, children: [
              Container(
                width: 62,
                height: 62,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(20),
                  gradient: gold ? const LinearGradient(colors: [Color(0xFFFBBF24), Color(0xFFF97316)]) : null,
                  color: gold ? null : (tier > 0 ? scheme.primary.withValues(alpha: 0.14) : scheme.surfaceContainerHighest),
                ),
                child: Icon(gameIcon('${b['icon']}'), size: 30, color: gold ? Colors.white : (tier > 0 ? scheme.primary : scheme.outline)),
              ),
              if (tier > 0)
                Positioned(
                  bottom: -8,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 1),
                    decoration: BoxDecoration(color: scheme.primary, borderRadius: BorderRadius.circular(8)),
                    child: Text('$tier-daraja', style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.w800)),
                  ),
                ),
            ]),
            const SizedBox(width: 16),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('${b['title_uz']}', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
                const SizedBox(height: 2),
                Text(next == null ? 'Eng yuqori daraja olingan! 🎉' : 'Keyingi: ${b['desc_uz']}',
                    style: TextStyle(color: scheme.outline, fontSize: 13)),
                const SizedBox(height: 8),
                ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(
                    value: ((b['pct'] as num) / 100).clamp(0.0, 1.0).toDouble(),
                    minHeight: 8,
                    backgroundColor: scheme.surfaceContainerHighest,
                    color: gold ? Brand.flame : scheme.primary,
                  ),
                ),
                const SizedBox(height: 4),
                Row(children: [
                  Text(next == null ? '${b['value']}' : '${b['value']} / $next', style: TextStyle(fontSize: 12, color: scheme.outline)),
                  const Spacer(),
                  for (var i = 0; i < tiers; i++)
                    Container(
                      width: 14,
                      height: 5,
                      margin: const EdgeInsets.only(left: 3),
                      decoration: BoxDecoration(
                        color: i < tier ? Brand.warn : scheme.surfaceContainerHighest,
                        borderRadius: BorderRadius.circular(3),
                      ),
                    ),
                ]),
              ]),
            ),
          ]),
        ),
      ),
    );
  }
}
