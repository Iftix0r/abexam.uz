import 'package:flutter/material.dart';

import '../core/app_state.dart';
import '../core/theme.dart';
import '../widgets/common.dart';
import 'lesson/input_steps.dart';

/// Every grammar explanation of the course, searchable.
class GrammarScreen extends StatefulWidget {
  const GrammarScreen({super.key});

  @override
  State<GrammarScreen> createState() => _GrammarScreenState();
}

class _GrammarScreenState extends State<GrammarScreen> {
  String _query = '';

  @override
  Widget build(BuildContext context) {
    final api = AppScope.read(context).api;
    return Scaffold(
      appBar: AppBar(title: const Text('Grammatika')),
      body: Loader<Map<String, dynamic>>(
        load: () => api.get('grammar/'),
        builder: (context, data, _) {
          final levels = (data['levels'] as List).cast<Map<String, dynamic>>();
          final q = _query.toLowerCase();
          return ListView(padding: const EdgeInsets.all(16), children: [
            TextField(
              decoration: const InputDecoration(prefixIcon: Icon(Icons.search_rounded), hintText: 'Qidirish: Present Perfect, too, articles...'),
              onChanged: (v) => setState(() => _query = v),
            ),
            for (final level in levels) ...[
              SectionTitle('${level['code']} · ${level['name']}'),
              for (final item in (level['items'] as List).cast<Map<String, dynamic>>())
                if (q.isEmpty || '${item['title_uz']} ${item['body_uz']}'.toLowerCase().contains(q))
                  Card(
                    margin: const EdgeInsets.only(bottom: 8),
                    child: ListTile(
                      leading: Icon(item['open'] == true ? Icons.lightbulb_rounded : Icons.lock_outline_rounded,
                          color: item['open'] == true ? Brand.level('${level['code']}') : Theme.of(context).colorScheme.outline),
                      title: Text('${item['title_uz']}', style: const TextStyle(fontWeight: FontWeight.w700)),
                      subtitle: Text('${item['lesson_title']}'),
                      onTap: () => showModalBottomSheet(
                        context: context,
                        isScrollControlled: true,
                        showDragHandle: true,
                        builder: (_) => DraggableScrollableSheet(
                          expand: false,
                          initialChildSize: 0.75,
                          maxChildSize: 0.95,
                          builder: (_, scroll) => ListView(
                            controller: scroll,
                            padding: const EdgeInsets.fromLTRB(18, 0, 18, 32),
                            children: [StepTitle('${item['title_uz']}'), GrammarCard(step: item)],
                          ),
                        ),
                      ),
                    ),
                  ),
            ],
          ]);
        },
      ),
    );
  }
}
