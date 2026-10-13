import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'core/app_state.dart';
import 'core/speech.dart';
import 'core/theme.dart';
import 'screens/auth_screen.dart';
import 'screens/home_shell.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(statusBarColor: Colors.transparent));
  final state = await AppState.load();
  Speech.instance.slow = state.slowSpeech;
  runApp(AbExamApp(state: state));
}

class AbExamApp extends StatelessWidget {
  const AbExamApp({super.key, required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) {
    return AppScope(
      state: state,
      child: MaterialApp(
        title: 'AbExam English',
        debugShowCheckedModeBanner: false,
        theme: buildTheme(Brightness.light),
        darkTheme: buildTheme(Brightness.dark),
        home: const _Gate(),
      ),
    );
  }
}

/// Shows the sign-in screen or the app depending on the saved token.
class _Gate extends StatelessWidget {
  const _Gate();

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 350),
      child: state.signedIn ? const HomeShell(key: ValueKey('home')) : const AuthScreen(key: ValueKey('auth')),
    );
  }
}
