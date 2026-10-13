import 'dart:math';

import 'package:flutter/material.dart';

/// One burst of confetti falling over its child (lesson finished well).
class Confetti extends StatefulWidget {
  const Confetti({super.key, required this.active, required this.child});

  final bool active;
  final Widget child;

  @override
  State<Confetti> createState() => _ConfettiState();
}

class _Piece {
  _Piece(Random r)
      : x = r.nextDouble(),
        delay = r.nextDouble() * 0.35,
        speed = 0.55 + r.nextDouble() * 0.6,
        drift = (r.nextDouble() - 0.5) * 0.25,
        spin = (r.nextDouble() - 0.5) * 12,
        size = 6 + r.nextDouble() * 6,
        color = _colors[r.nextInt(_colors.length)];

  static const _colors = [
    Color(0xFF6366F1), Color(0xFF8B5CF6), Color(0xFFF59E0B), Color(0xFF10B981),
    Color(0xFFEC4899), Color(0xFF3B82F6), Color(0xFFF97316),
  ];

  final double x, delay, speed, drift, spin, size;
  final Color color;
}

class _ConfettiState extends State<Confetti> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 2600));
  final _pieces = List.generate(90, (_) => _Piece(Random()));

  @override
  void initState() {
    super.initState();
    if (widget.active) _c.forward();
  }

  @override
  void didUpdateWidget(Confetti old) {
    super.didUpdateWidget(old);
    if (widget.active && !old.active) _c.forward(from: 0);
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Stack(children: [
      widget.child,
      Positioned.fill(
        child: IgnorePointer(
          child: AnimatedBuilder(
            animation: _c,
            builder: (_, _) => _c.isAnimating ? CustomPaint(painter: _ConfettiPainter(_pieces, _c.value)) : const SizedBox(),
          ),
        ),
      ),
    ]);
  }
}

class _ConfettiPainter extends CustomPainter {
  _ConfettiPainter(this.pieces, this.t);

  final List<_Piece> pieces;
  final double t;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint();
    for (final p in pieces) {
      final local = ((t - p.delay) / (1 - p.delay)).clamp(0.0, 1.0);
      if (local <= 0) continue;
      final y = -20 + local * p.speed * (size.height + 60);
      final x = (p.x + p.drift * local + sin(local * 8 + p.x * 10) * 0.02) * size.width;
      paint.color = p.color.withValues(alpha: 1 - max(0, local - 0.75) * 4);
      canvas.save();
      canvas.translate(x, y);
      canvas.rotate(p.spin * local);
      canvas.drawRRect(
        RRect.fromRectAndRadius(Rect.fromCenter(center: Offset.zero, width: p.size, height: p.size * 0.55), const Radius.circular(1.5)),
        paint,
      );
      canvas.restore();
    }
  }

  @override
  bool shouldRepaint(_ConfettiPainter old) => old.t != t;
}
