# AbExam English — mobil ilova (Flutter)

abexam.uz saytidagi ingliz tili kursining (`/learn/`) mobil ilovasi. Barcha kontent,
XP, seriya, so'zlar va natijalar server bilan umumiy — saytda boshlagan darsni
ilovada davom ettirish mumkin.

## Imkoniyatlar
- **Darslar** — A1–C2 yo'li, barcha mashq turlari: so'zlar, dialog, o'qish, grammatika,
  test, bo'sh joy, gap tuzish, juftlik, diktant, tarjima, gapirish (ovozni tanish), yozish (AI tekshiruv).
- **Xatolar ustida ishlash** — aralash mashq.
- **So'zlarni takrorlash** — spaced repetition kartochkalar.
- **Hikoyalar** — tinglash, tarjima, savollar.
- **AI suhbatdosh** — 6 ta vaziyat, xatolarni tuzatish, ovozli kiritish.
- **Profil** — kunlik maqsad, reyting, grammatika ma'lumotnomasi, daraja testi.

Talaffuz va audio telefonning o'zida ishlaydi (`flutter_tts`, `speech_to_text`), serverga yuk yo'q.

## Ishga tushirish
```bash
cd mobile
flutter pub get
flutter run                                              # https://abexam.uz bilan
flutter run --dart-define=API_BASE=http://10.0.2.2:8000  # lokal Django (Android emulyator)
```

## Build
```bash
flutter build apk --release --dart-define=API_BASE=https://abexam.uz
flutter build appbundle --release        # Google Play uchun
```
Release uchun `android/app/build.gradle.kts` da o'z imzo kalitingizni (signingConfig) sozlang.

## Server API
`learn/api.py` — `/api/learn/...`, `Authorization: Bearer <token>`.
Token login/ro'yxatdan o'tishda beriladi; admin paneldagi "Ilova tokenlari" orqali qurilmani chiqarib yuborish mumkin.
