import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
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

  void _switch(bool register) {
    if (register == _register) return;
    HapticFeedback.selectionClick();
    setState(() {
      _register = register;
      _error = null;
    });
  }

  Future<void> _submit() async {
    FocusScope.of(context).unfocus();
    if (!_form.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final state = AppScope.read(context);
    try {
      if (_register) {
        await state.register({
          for (final e in _c.entries) e.key: e.key.contains('password') ? e.value.text : e.value.text.trim(),
        });
      } else {
        await state.signIn(_c['username']!.text.trim(), _c['password']!.text);
      }
    } on ApiException catch (e) {
      HapticFeedback.heavyImpact();
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light,
      child: Scaffold(
        backgroundColor: Brand.primaryDeep,
        body: Container(
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              colors: [Color(0xFF4338CA), Color(0xFF6D28D9), Color(0xFF7C3AED)],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
          ),
          child: Stack(children: [
            const _Decor(),
            SafeArea(
              bottom: false,
              child: LayoutBuilder(
                builder: (context, box) => SingleChildScrollView(
                  keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
                  child: ConstrainedBox(
                    constraints: BoxConstraints(minHeight: box.maxHeight),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [_Header(compact: _register), _panel(scheme)],
                    ),
                  ),
                ),
              ),
            ),
          ]),
        ),
      ),
    );
  }

  Widget _panel(ColorScheme scheme) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    return Container(
      width: double.infinity,
      padding: EdgeInsets.fromLTRB(22, 26, 22, 18 + MediaQuery.paddingOf(context).bottom),
      decoration: BoxDecoration(
        color: dark ? const Color(0xFF12142A) : Colors.white,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(32)),
        boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.18), blurRadius: 30, offset: const Offset(0, -6))],
      ),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 460),
          child: Form(
            key: _form,
            child: AnimatedSize(
              duration: const Duration(milliseconds: 300),
              curve: Curves.easeOutCubic,
              alignment: Alignment.topCenter,
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                AnimatedSwitcher(
                  duration: const Duration(milliseconds: 250),
                  child: Column(
                    key: ValueKey(_register),
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(_register ? 'Hisob yarating ✨' : 'Xush kelibsiz! 👋',
                          style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w900, letterSpacing: -0.5)),
                      const SizedBox(height: 4),
                      Text(
                        _register ? "Bir daqiqada ro'yxatdan o'ting va bepul boshlang" : 'Hisobingizga kiring va o\'qishni davom ettiring',
                        style: TextStyle(color: scheme.outline, fontSize: 15),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 20),
                _ModeToggle(register: _register, onChanged: _switch),
                const SizedBox(height: 20),
                if (_register) ...[
                  Row(children: [
                    Expanded(child: _field('first_name', 'Ism', Icons.badge_outlined, capitalize: true)),
                    const SizedBox(width: 10),
                    Expanded(child: _field('last_name', 'Familiya', null, required: false, capitalize: true)),
                  ]),
                  _field('phone_number', 'Telefon (ixtiyoriy)', Icons.phone_iphone_rounded,
                      required: false, keyboard: TextInputType.phone, hint: '+998 90 123 45 67'),
                ],
                _field('username', 'Login', Icons.alternate_email_rounded,
                    hint: _register ? 'masalan: ali_2007' : null, autofill: AutofillHints.username),
                _field('password', 'Parol', Icons.lock_rounded,
                    password: true, autofill: _register ? AutofillHints.newPassword : AutofillHints.password),
                if (_register)
                  _field('confirm_password', 'Parolni takrorlang', Icons.lock_reset_rounded, password: true)
                else
                  Align(
                    alignment: Alignment.centerRight,
                    child: TextButton(
                      style: TextButton.styleFrom(visualDensity: VisualDensity.compact),
                      onPressed: () => launchUrl(Uri.parse('$apiBase/password-reset/'), mode: LaunchMode.externalApplication),
                      child: const Text('Parolni unutdingizmi?'),
                    ),
                  ),
                if (_register)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 6, left: 4),
                    child: Text('Parol kamida 8 belgi, faqat raqamlardan iborat bo\'lmasin.',
                        style: TextStyle(color: scheme.outline, fontSize: 12.5)),
                  ),
                AnimatedSwitcher(
                  duration: const Duration(milliseconds: 250),
                  child: _error == null
                      ? const SizedBox(width: double.infinity, height: 8)
                      : Container(
                          key: ValueKey(_error),
                          margin: const EdgeInsets.only(top: 6, bottom: 12),
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: Brand.bad.withValues(alpha: dark ? 0.18 : 0.08),
                            borderRadius: BorderRadius.circular(14),
                            border: Border.all(color: Brand.bad.withValues(alpha: 0.35)),
                          ),
                          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            const Icon(Icons.error_outline_rounded, color: Brand.bad, size: 20),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text(_error!,
                                  style: TextStyle(color: dark ? const Color(0xFFFCA5A5) : Brand.bad, fontWeight: FontWeight.w600, height: 1.35)),
                            ),
                          ]),
                        ),
                ),
                _GradientButton(
                  label: _register ? "Ro'yxatdan o'tish" : 'Kirish',
                  busy: _busy,
                  onPressed: _submit,
                ),
                const SizedBox(height: 16),
                Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                  Text(_register ? 'Hisobingiz bormi?' : "Hisobingiz yo'qmi?", style: TextStyle(color: scheme.outline)),
                  TextButton(
                    style: TextButton.styleFrom(visualDensity: VisualDensity.compact),
                    onPressed: () => _switch(!_register),
                    child: Text(_register ? 'Kirish' : "Ro'yxatdan o'tish", style: const TextStyle(fontWeight: FontWeight.w800)),
                  ),
                ]),
                Text('abexam.uz saytidagi hisob bilan bir xil — natijalaringiz umumiy.',
                    textAlign: TextAlign.center, style: TextStyle(color: scheme.outline, fontSize: 12)),
              ]),
            ),
          ),
        ),
      ),
    );
  }

  Widget _field(
    String key,
    String label,
    IconData? icon, {
    bool password = false,
    bool required = true,
    bool capitalize = false,
    TextInputType? keyboard,
    String? hint,
    String? autofill,
  }) {
    final scheme = Theme.of(context).colorScheme;
    final dark = Theme.of(context).brightness == Brightness.dark;
    final last = (!_register && key == 'password') || (_register && key == 'confirm_password');
    final radius = BorderRadius.circular(16);
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: TextFormField(
        controller: _c[key],
        obscureText: password && _hidePassword,
        keyboardType: keyboard,
        autocorrect: false,
        enableSuggestions: !password,
        textCapitalization: capitalize ? TextCapitalization.words : TextCapitalization.none,
        autofillHints: autofill == null ? null : [autofill],
        textInputAction: last ? TextInputAction.done : TextInputAction.next,
        onFieldSubmitted: last ? (_) => _submit() : null,
        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
        decoration: InputDecoration(
          labelText: label,
          hintText: hint,
          filled: true,
          fillColor: dark ? const Color(0xFF1C1F3A) : const Color(0xFFF3F4FA),
          prefixIcon: icon == null ? null : Icon(icon, color: scheme.primary.withValues(alpha: 0.8)),
          suffixIcon: password
              ? IconButton(
                  icon: Icon(_hidePassword ? Icons.visibility_rounded : Icons.visibility_off_rounded, color: scheme.outline),
                  onPressed: () => setState(() => _hidePassword = !_hidePassword),
                )
              : null,
          border: OutlineInputBorder(borderRadius: radius, borderSide: BorderSide.none),
          enabledBorder: OutlineInputBorder(borderRadius: radius, borderSide: BorderSide.none),
          focusedBorder: OutlineInputBorder(borderRadius: radius, borderSide: BorderSide(color: scheme.primary, width: 2)),
          errorBorder: OutlineInputBorder(borderRadius: radius, borderSide: const BorderSide(color: Brand.bad)),
          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
        ),
        validator: (v) {
          if (required && (v == null || v.trim().isEmpty)) return "To'ldiring";
          if (key == 'confirm_password' && v != _c['password']!.text) return 'Parollar mos emas';
          return null;
        },
      ),
    );
  }
}

/// Logo, name and what the app offers.
class _Header extends StatelessWidget {
  const _Header({required this.compact});

  final bool compact;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 28, 24, 28),
      child: TweenAnimationBuilder<double>(
        tween: Tween(begin: 0, end: 1),
        duration: const Duration(milliseconds: 700),
        curve: Curves.easeOutCubic,
        builder: (_, v, child) => Opacity(opacity: v, child: Transform.translate(offset: Offset(0, 20 * (1 - v)), child: child)),
        child: Column(children: [
          AnimatedContainer(
            duration: const Duration(milliseconds: 300),
            width: compact ? 64 : 84,
            height: compact ? 64 : 84,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(compact ? 20 : 26),
              boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.18), blurRadius: 20, offset: const Offset(0, 6))],
            ),
            clipBehavior: Clip.antiAlias,
            child: Image.asset('assets/icon/icon.png', fit: BoxFit.cover),
          ),
          const SizedBox(height: 14),
          const Text('AbExam English',
              style: TextStyle(color: Colors.white, fontSize: 28, fontWeight: FontWeight.w900, letterSpacing: -0.5)),
          const SizedBox(height: 4),
          Text('Ingliz tili · A1 dan C2 gacha', style: TextStyle(color: Colors.white.withValues(alpha: 0.8), fontSize: 15)),
          AnimatedSize(
            duration: const Duration(milliseconds: 300),
            child: compact
                ? const SizedBox(width: double.infinity)
                : const Padding(
                    padding: EdgeInsets.only(top: 18),
                    child: Wrap(alignment: WrapAlignment.center, spacing: 8, runSpacing: 8, children: [
                      _Feature(icon: Icons.headphones_rounded, text: 'Tinglash'),
                      _Feature(icon: Icons.mic_rounded, text: 'Gapirish'),
                      _Feature(icon: Icons.auto_awesome_rounded, text: 'AI ustoz'),
                      _Feature(icon: Icons.local_fire_department_rounded, text: 'Har kuni 10 daq'),
                    ]),
                  ),
          ),
        ]),
      ),
    );
  }
}

class _Feature extends StatelessWidget {
  const _Feature({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Colors.white.withValues(alpha: 0.2)),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(icon, size: 15, color: Colors.white),
        const SizedBox(width: 5),
        Text(text, style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w600)),
      ]),
    );
  }
}

/// Faint English words and soft circles behind the header.
class _Decor extends StatelessWidget {
  const _Decor();

  @override
  Widget build(BuildContext context) {
    Widget word(String t, double size, double angle) => Transform.rotate(
          angle: angle,
          child: Text(t, style: TextStyle(color: Colors.white.withValues(alpha: 0.09), fontSize: size, fontWeight: FontWeight.w900)),
        );
    Widget circle(double d, double a) => Container(
          width: d,
          height: d,
          decoration: BoxDecoration(shape: BoxShape.circle, color: Colors.white.withValues(alpha: a)),
        );
    return IgnorePointer(
      child: Stack(children: [
        Positioned(top: -60, right: -40, child: circle(220, 0.07)),
        Positioned(top: 180, left: -70, child: circle(160, 0.05)),
        Positioned(top: 70, left: 18, child: word('Hello!', 30, -0.2)),
        Positioned(top: 120, right: 16, child: word('IELTS', 26, 0.18)),
        Positioned(top: 250, right: 30, child: word('Speak', 24, -0.12)),
        Positioned(top: 285, left: 26, child: word('B2', 34, 0.1)),
      ]),
    );
  }
}

/// Sliding two-option switch: Kirish / Ro'yxatdan o'tish.
class _ModeToggle extends StatelessWidget {
  const _ModeToggle({required this.register, required this.onChanged});

  final bool register;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final scheme = Theme.of(context).colorScheme;
    Widget label(String text, bool value) => Expanded(
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () => onChanged(value),
            child: Center(
              child: AnimatedDefaultTextStyle(
                duration: const Duration(milliseconds: 200),
                style: DefaultTextStyle.of(context).style.copyWith(
                  fontSize: 15,
                  fontWeight: FontWeight.w800,
                  color: register == value ? scheme.primary : scheme.outline,
                ),
                child: Text(text, maxLines: 1),
              ),
            ),
          ),
        );
    return Container(
      height: 50,
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: dark ? const Color(0xFF1C1F3A) : const Color(0xFFF0F1F8),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Stack(children: [
        AnimatedAlign(
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOutCubic,
          alignment: register ? Alignment.centerRight : Alignment.centerLeft,
          child: FractionallySizedBox(
            widthFactor: 0.5,
            child: Container(
              decoration: BoxDecoration(
                color: dark ? const Color(0xFF2A2E52) : Colors.white,
                borderRadius: BorderRadius.circular(12),
                boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.08), blurRadius: 8, offset: const Offset(0, 2))],
              ),
            ),
          ),
        ),
        Row(children: [label('Kirish', false), label("Ro'yxatdan o'tish", true)]),
      ]),
    );
  }
}

class _GradientButton extends StatelessWidget {
  const _GradientButton({required this.label, required this.busy, required this.onPressed});

  final String label;
  final bool busy;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 56,
      decoration: BoxDecoration(
        gradient: Brand.heroGradient,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [BoxShadow(color: Brand.primary.withValues(alpha: 0.3), blurRadius: 14, offset: const Offset(0, 4))],
      ),
      child: Material(
        type: MaterialType.transparency,
        child: InkWell(
          borderRadius: BorderRadius.circular(16),
          onTap: busy ? null : onPressed,
          child: Center(
            child: busy
                ? const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2.5, color: Colors.white))
                : Row(mainAxisSize: MainAxisSize.min, children: [
                    Text(label, style: const TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w800)),
                    const SizedBox(width: 8),
                    const Icon(Icons.arrow_forward_rounded, color: Colors.white, size: 20),
                  ]),
          ),
        ),
      ),
    );
  }
}
