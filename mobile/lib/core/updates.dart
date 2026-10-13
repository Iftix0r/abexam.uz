import 'package:flutter/material.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:url_launcher/url_launcher.dart';

import 'app_state.dart';

/// Asks the server for the newest build (published in the admin panel) and
/// offers it. A skipped version isn't offered again unless it's mandatory.
Future<void> checkForUpdate(BuildContext context) async {
  final state = AppScope.read(context);
  try {
    final info = await state.api.get('app-version/');
    final build = (info['build'] as num?)?.toInt() ?? 0;
    final mine = int.tryParse((await PackageInfo.fromPlatform()).buildNumber) ?? 0;
    final force = info['force'] == true;
    final skipped = (state.readJson('cache:update-skipped')?['build'] as num?)?.toInt();
    if (build <= mine || (!force && skipped == build) || !context.mounted) return;
    final notes = ((info['notes'] as List?) ?? []).map((e) => '$e').toList();
    final update = await showDialog<bool>(
      context: context,
      barrierDismissible: !force,
      builder: (c) => PopScope(
        canPop: !force,
        child: AlertDialog(
          icon: const Icon(Icons.system_update_rounded, size: 36),
          title: Text('Yangi versiya: ${info['version']}'),
          content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            if (force) const Text("Bu versiya majburiy — davom etish uchun ilovani yangilang.\n"),
            for (final n in notes.take(6)) Padding(padding: const EdgeInsets.only(bottom: 4), child: Text('• $n')),
            if (notes.isEmpty) const Text('Yangi imkoniyatlar va tuzatishlar.'),
          ]),
          actions: [
            if (!force) TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Keyinroq')),
            FilledButton.icon(
              onPressed: () => Navigator.pop(c, true),
              icon: const Icon(Icons.download_rounded),
              label: const Text('Yangilash'),
            ),
          ],
        ),
      ),
    );
    if (update == true) {
      await launchUrl(Uri.parse('${info['url']}'), mode: LaunchMode.externalApplication);
    } else {
      await state.writeJson('cache:update-skipped', {'build': build});
    }
  } catch (_) {
    // No network or no release yet — try again next launch.
  }
}
