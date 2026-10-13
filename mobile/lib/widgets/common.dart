import 'dart:async';

import 'package:flutter/material.dart';

import '../core/api.dart';
import '../core/speech.dart';
import '../core/theme.dart';

/// Loads data with [load], showing a spinner, a friendly error with retry,
/// and pull-to-refresh-ready content.
class Loader<T> extends StatefulWidget {
  const Loader({super.key, required this.load, required this.builder});

  final Future<T> Function() load;
  final Widget Function(BuildContext context, T data, Future<void> Function() reload) builder;

  @override
  State<Loader<T>> createState() => _LoaderState<T>();
}

class _LoaderState<T> extends State<Loader<T>> {
  T? _data;
  Object? _error;
  bool _loading = true;
  bool _slow = false;
  Timer? _slowTimer;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  @override
  void dispose() {
    _slowTimer?.cancel();
    super.dispose();
  }

  Future<void> _reload() async {
    setState(() {
      _loading = _data == null;
      _error = null;
      _slow = false;
    });
    _slowTimer?.cancel();
    _slowTimer = Timer(const Duration(seconds: 4), () {
      if (mounted) setState(() => _slow = true);
    });
    try {
      final data = await widget.load();
      if (mounted) setState(() => _data = data);
    } catch (e) {
      if (mounted) setState(() => _error = e);
    } finally {
      _slowTimer?.cancel();
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return LoadingView(slow: _slow);
    if (_error != null && _data == null) return ErrorView(error: _error!, onRetry: _reload);
    return widget.builder(context, _data as T, _reload);
  }
}

class LoadingView extends StatelessWidget {
  const LoadingView({super.key, this.slow = false});

  /// After a few seconds, explain the wait (first connection passes the hosting check).
  final bool slow;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        const CircularProgressIndicator(),
        AnimatedOpacity(
          opacity: slow ? 1 : 0,
          duration: const Duration(milliseconds: 400),
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Text('Serverga ulanmoqda...\nBirinchi ulanish bir necha soniya olishi mumkin.',
                textAlign: TextAlign.center, style: TextStyle(color: Theme.of(context).colorScheme.outline)),
          ),
        ),
      ]),
    );
  }
}

class ErrorView extends StatelessWidget {
  const ErrorView({super.key, required this.error, this.onRetry});

  final Object error;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final msg = error is ApiException ? error.toString() : "Nimadir xato ketdi. Qayta urinib ko'ring.";
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Icon(Icons.cloud_off_rounded, size: 56, color: Theme.of(context).colorScheme.outline),
          const SizedBox(height: 16),
          Text(msg, textAlign: TextAlign.center, style: Theme.of(context).textTheme.bodyLarge),
          if (onRetry != null) ...[
            const SizedBox(height: 20),
            OutlinedButton.icon(onPressed: onRetry, icon: const Icon(Icons.refresh_rounded), label: const Text('Qayta urinish')),
          ],
        ]),
      ),
    );
  }
}

void showError(BuildContext context, Object error) {
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
    content: Text(error is ApiException ? error.message : "Xatolik yuz berdi"),
    backgroundColor: Brand.bad,
  ));
}

/// Round speaker button that reads [text] aloud.
class SayButton extends StatelessWidget {
  const SayButton(this.text, {super.key, this.size = 20, this.rate = 1});

  final String text;
  final double size;
  final double rate;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return IconButton(
      visualDensity: VisualDensity.compact,
      tooltip: 'Tinglash',
      style: IconButton.styleFrom(backgroundColor: scheme.primary.withValues(alpha: 0.1)),
      icon: Icon(Icons.volume_up_rounded, size: size, color: scheme.primary),
      onPressed: () => Speech.instance.say(text, rate: rate),
    );
  }
}

/// Big circular play button pair (normal + slow) for listening exercises.
class PlayButtons extends StatelessWidget {
  const PlayButtons(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Row(mainAxisAlignment: MainAxisAlignment.center, children: [
      _round(context, Icons.volume_up_rounded, 84, () => Speech.instance.say(text)),
      const SizedBox(width: 16),
      _round(context, Icons.slow_motion_video_rounded, 56, () => Speech.instance.say(text, rate: 0.65)),
    ]);
  }

  Widget _round(BuildContext context, IconData icon, double size, VoidCallback onTap) {
    return Material(
      shape: const CircleBorder(),
      clipBehavior: Clip.antiAlias,
      child: Ink(
        decoration: const BoxDecoration(gradient: Brand.heroGradient, shape: BoxShape.circle),
        child: InkWell(
          onTap: onTap,
          child: SizedBox(width: size, height: size, child: Icon(icon, color: Colors.white, size: size * 0.45)),
        ),
      ),
    );
  }
}

class Pill extends StatelessWidget {
  const Pill({super.key, required this.label, this.icon, this.color});

  final String label;
  final IconData? icon;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final c = color ?? Theme.of(context).colorScheme.primary;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(color: c.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(999)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        if (icon != null) ...[Icon(icon, size: 15, color: c), const SizedBox(width: 4)],
        Text(label, style: TextStyle(color: c, fontWeight: FontWeight.w700, fontSize: 13)),
      ]),
    );
  }
}

class SectionTitle extends StatelessWidget {
  const SectionTitle(this.text, {super.key, this.trailing});

  final String text;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 24, 4, 10),
      child: Row(children: [
        Expanded(child: Text(text, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800))),
        ?trailing,
      ]),
    );
  }
}

/// Maps the course's lucide icon names to Material icons.
IconData unitIcon(String name) {
  const map = {
    'hand': Icons.waving_hand_rounded,
    'house': Icons.home_rounded,
    'utensils': Icons.restaurant_rounded,
    'shopping-bag': Icons.shopping_bag_rounded,
    'users': Icons.groups_rounded,
    'shirt': Icons.checkroom_rounded,
    'calendar': Icons.calendar_month_rounded,
    'history': Icons.history_edu_rounded,
    'message-square': Icons.forum_rounded,
    'heart-pulse': Icons.monitor_heart_rounded,
    'briefcase': Icons.work_rounded,
    'globe': Icons.public_rounded,
    'target': Icons.track_changes_rounded,
    'graduation-cap': Icons.school_rounded,
    'pen-tool': Icons.edit_note_rounded,
    'sparkles': Icons.auto_awesome_rounded,
    'trophy': Icons.emoji_events_rounded,
    'layers': Icons.layers_rounded,
    'crown': Icons.workspace_premium_rounded,
    'book-marked': Icons.bookmark_rounded,
    'feather': Icons.history_edu_rounded,
  };
  return map[name] ?? Icons.menu_book_rounded;
}
