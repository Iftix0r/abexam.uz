import 'package:flutter/material.dart';

import '../core/app_state.dart';
import 'learn_tab.dart';
import 'profile_tab.dart';
import 'review_screen.dart';
import 'stories_tab.dart';
import 'tutor_tab.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _tab = 0;
  final _learnKey = GlobalKey<LearnTabState>();

  @override
  void initState() {
    super.initState();
    AppScope.read(context).refresh().catchError((_) {});
  }

  void goTo(int tab) => setState(() => _tab = tab);

  @override
  Widget build(BuildContext context) {
    final me = AppScope.of(context).me;
    final due = ((me?['review'] as Map?)?['session'] as int?) ?? 0;
    final pages = [
      LearnTab(key: _learnKey, onOpenReview: () => goTo(1)),
      ReviewTab(active: _tab == 1),
      const StoriesTab(),
      const TutorTab(),
      const ProfileTab(),
    ];
    return Scaffold(
      body: IndexedStack(index: _tab, children: pages),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (i) {
          if (i == 0 && _tab == 0) _learnKey.currentState?.reload();
          goTo(i);
        },
        destinations: [
          const NavigationDestination(icon: Icon(Icons.school_outlined), selectedIcon: Icon(Icons.school_rounded), label: 'Darslar'),
          NavigationDestination(
            icon: Badge(isLabelVisible: due > 0, label: Text('$due'), child: const Icon(Icons.style_outlined)),
            selectedIcon: const Icon(Icons.style_rounded),
            label: "So'zlar",
          ),
          const NavigationDestination(icon: Icon(Icons.auto_stories_outlined), selectedIcon: Icon(Icons.auto_stories_rounded), label: 'Hikoyalar'),
          const NavigationDestination(icon: Icon(Icons.forum_outlined), selectedIcon: Icon(Icons.forum_rounded), label: 'AI suhbat'),
          const NavigationDestination(icon: Icon(Icons.person_outline_rounded), selectedIcon: Icon(Icons.person_rounded), label: 'Profil'),
        ],
      ),
    );
  }
}
