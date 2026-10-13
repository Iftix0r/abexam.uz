import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../core/api.dart';
import '../core/app_state.dart';
import '../core/theme.dart';

class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key});

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  bool _register = false;
  bool _busy = false;
  bool _hidePassword = true;
  String? _error;
  final _form = GlobalKey<FormState>();
  final _c = {
    for (final k in ['username', 'password', 'confirm_password', 'first_name', 'last_name', 'phone_number'])
      k: TextEditingController(),
  };

  @override
  void dispose() {
    for (final c in _c.values) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_form.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final state = AppScope.read(context);
    try {
      if (_register) {
        await state.register({for (final e in _c.entries) e.key: e.value.text.trim()});
      } else {
        await state.signIn(_c['username']!.text.trim(), _c['password']!.text);
      }
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: Stack(children: [
        Container(height: 320, decoration: const BoxDecoration(gradient: Brand.heroGradient)),
        SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(20),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 460),
                child: Column(children: [
                  const SizedBox(height: 8),
                  Container(
                    width: 76,
                    height: 76,
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.18),
                      borderRadius: BorderRadius.circular(24),
                    ),
                    child: const Icon(Icons.translate_rounded, color: Colors.white, size: 40),
                  ),
                  const SizedBox(height: 14),
                  const Text('AbExam English',
                      style: TextStyle(color: Colors.white, fontSize: 28, fontWeight: FontWeight.w900)),
                  const SizedBox(height: 6),
                  Text("A1 dan C2 gacha — har kuni 10 daqiqa",
                      style: TextStyle(color: Colors.white.withValues(alpha: 0.85), fontSize: 15)),
                  const SizedBox(height: 28),
                  Card(
                    elevation: 6,
                    shadowColor: Colors.black26,
                    child: Padding(
                      padding: const EdgeInsets.all(20),
                      child: Form(
                        key: _form,
                        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                          SegmentedButton<bool>(
                            segments: const [
                              ButtonSegment(value: false, label: Text('Kirish', maxLines: 1)),
                              ButtonSegment(value: true, label: Text("Ro'yxatdan o'tish", maxLines: 1, softWrap: false)),
                            ],
                            selected: {_register},
                            showSelectedIcon: false,
                            onSelectionChanged: (s) => setState(() {
                              _register = s.first;
                              _error = null;
                            }),
                          ),
                          const SizedBox(height: 20),
                          if (_register) ...[
                            _field('first_name', 'Ismingiz', Icons.badge_outlined),
                            _field('last_name', 'Familiyangiz', Icons.badge_outlined, required: false),
                            _field('phone_number', 'Telefon (+998...)', Icons.phone_outlined,
                                required: false, keyboard: TextInputType.phone),
                          ],
                          _field('username', 'Foydalanuvchi nomi (login)', Icons.person_outline_rounded),
                          _field('password', 'Parol', Icons.lock_outline_rounded, password: true),
                          if (_register) _field('confirm_password', 'Parolni takrorlang', Icons.lock_outline_rounded, password: true),
                          if (_error != null)
                            Container(
                              margin: const EdgeInsets.only(bottom: 14),
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(color: Brand.badSoft, borderRadius: BorderRadius.circular(12)),
                              child: Text(_error!, style: const TextStyle(color: Brand.bad, fontWeight: FontWeight.w600)),
                            ),
                          FilledButton(
                            onPressed: _busy ? null : _submit,
                            child: _busy
                                ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.5))
                                : Text(_register ? "Ro'yxatdan o'tish" : 'Kirish'),
                          ),
                          if (!_register)
                            TextButton(
                              onPressed: () => launchUrl(Uri.parse('$apiBase/password-reset/'), mode: LaunchMode.externalApplication),
                              child: const Text('Parolni unutdingizmi?'),
                            ),
                          const SizedBox(height: 4),
                          Text(
                            "abexam.uz saytidagi login va parolingiz bilan kiring — natijalaringiz sayt bilan umumiy.",
                            textAlign: TextAlign.center,
                            style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.outline),
                          ),
                        ]),
                      ),
                    ),
                  ),
                ]),
              ),
            ),
          ),
        ),
      ]),
    );
  }

  Widget _field(String key, String label, IconData icon,
      {bool password = false, bool required = true, TextInputType? keyboard}) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: TextFormField(
        controller: _c[key],
        obscureText: password && _hidePassword,
        keyboardType: keyboard,
        autocorrect: false,
        enableSuggestions: !password,
        textInputAction: TextInputAction.next,
        onFieldSubmitted: password && (!_register || key == 'confirm_password') ? (_) => _submit() : null,
        decoration: InputDecoration(
          labelText: label,
          prefixIcon: Icon(icon),
          suffixIcon: password
              ? IconButton(
                  icon: Icon(_hidePassword ? Icons.visibility_outlined : Icons.visibility_off_outlined),
                  onPressed: () => setState(() => _hidePassword = !_hidePassword),
                )
              : null,
        ),
        validator: (v) => required && (v == null || v.trim().isEmpty) ? "To'ldiring" : null,
      ),
    );
  }
}
