# 🎯 AbExam.uz — IELTS Mock & Gamified English Learning Platform

<p align="center">
  <img src="static/favicon.svg" alt="AbExam Logo" width="96" height="96" />
</p>

<p align="center">
  <b>IELTS Mock imtihonlari, interaktiv ingliz tili darslari (SRS), so'z o'yinlari, real-vaqtli talabalar chati va Flutter mobil ilovasini o'zida birlashtirgan zamonaviy ta'lim ekotizimi.</b>
</p>

<p align="center">
  <a href="https://abexam.uz"><img src="https://img.shields.io/badge/Sayt-abexam.uz-d32f2f?style=for-the-badge&logo=googlechrome&logoColor=white" alt="Live Site"></a>
  <img src="https://img.shields.io/badge/Python-3.11%20%7C%203.14-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Django-4.2-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django">
  <img src="https://img.shields.io/badge/Flutter-Cross--Platform-02569B?style=for-the-badge&logo=flutter&logoColor=white" alt="Flutter">
  <img src="https://img.shields.io/badge/OpenAI-GPT--4o-412991?style=for-the-badge&logo=openai&logoColor=white" alt="OpenAI">
</p>

---

## 📑 Mundarija

- [Loyiha haqida](#-loyiha-haqida)
- [Asosiy imkoniyatlar](#-asosiy-imkoniyatlar)
  - [1. IELTS Mock & Practice Testlar](#1-ielts-mock--practice-testlar)
  - [2. Interaktiv kurslar (Learn — Duolingo uslubida)](#2-interaktiv-kurslar-learn--duolingo-uslubida)
  - [3. AbChat — Talabalar hamjamiyati](#3-abchat--talabalar-hamjamiyati)
  - [4. AB Games — So'z o'yinlari](#4-ab-games--soz-oyinlari)
  - [5. Boshqaruv paneli (Control Panel)](#5-boshqaruv-paneli-control-panel)
  - [6. Flutter mobil ilovasi](#6-flutter-mobil-ilovasi)
  - [7. Telegram Bot integratsiyasi](#7-telegram-bot-integratsiyasi)
- [Texnologiyalar to'plami (Tech Stack)](#-texnologiyalar-toplami-tech-stack)
- [Loyiha tuzilishi](#-loyiha-tuzilishi)
- [O'rnatish va mahalliy ishga tushirish](#-ornatish-va-mahalliy-ishga-tushirish)
- [Muhit o'zgaruvchilari (.env)](#-muhit-ozgaruvchilari-env)
- [Serverga joylash (Deployment)](#-serverga-joylash-deployment)
- [Litsenziya va muallif](#-litsenziya-va-muallif)

---

## 💡 Loyiha haqida

**AbExam** — bu IELTS imtihonlariga tayyorlanuvchi va ingliz tilini noldan professional darajagacha (A1–C2) o'rganuvchilar uchun yaratilgan keng qamrovli veb va mobil platforma.

Platforma orqali talabalar real IELTS formatidagi to'liq mock testlarni topshirishlari, har bir bo'lim (Reading, Listening, Writing, Speaking) bo'yicha alohida mashq qilishlari, AI tyutori yordamida o'z xatolarini tahlil qilishlari va butun respublika miqyosidagi umumiy reytingda o'zaro bellashishlari mumkin.

---

## ✨ Asosiy imkoniyatlar

### 1. IELTS Mock & Practice Testlar
- **Barcha bo'limlar**: Listening (audio pleyer bilan), Reading (matn va savollar ikki ustunda), Writing (Task 1 va Task 2) hamda Speaking.
- **Rasmiy baholash algoritmi**: IELTS 9.0 shkalasi bo'yicha to'g'ri hisob-kitoblar.
- **Kamera nazorati (Anti-cheat)**: Imtihon paytida veb-kamera ruxsati va onlayn kuzatuv tizimi.
- **Cambridge materiallari bazasi**: Cambridge IELTS 17, 18 va maxsus mock to'plamlari avtomatik yuklangan.
- **Umumiy & Oylik Reyting**: Barcha talabalar natijalari, podium (1, 2, 3-o'rinlar), shaxsiy o'rin va yutuqlar ro'yxati.

### 2. Interaktiv kurslar (Learn — Duolingo uslubida)
- **A1–C2 bosqichli yo'l**: Mikro-darslar, grammatik qoidalar va leksik mashqlar.
- **SRS (Spaced Repetition System)**: Unutilayotgan so'zlarni aqlli vaqt oralig'ida qaytarish mexanizmi.
- **Gamifikatsiya**: XP ballar, kunlik seriya (streak), hayotlar (hearts), muzlatgich (freeze) va haftalik XP liga jadvali.
- **AI Tushuntirish ("Explain My Answer")**: Xato javob berilganda GPT yordamida har bir variantning izohi.

### 3. AbChat — Talabalar hamjamiyati
- **Umumiy zal va Shaxsiy yozishmalar**: Real-vaqtli xabarlar, reaktsiyalar, xabarlarni qadash (pin) va qidiruv.
- **Onlayn holat & Stories**: Faol talabalar avatar lentasi, onlayn indikatorlar.
- **Xavfsiz profil kartalari**: O'quvchilar telefon raqamlari sir saqlangan holda jamoat ismlari va yutuqlar bilan muloqot qiladi.
- **AB Admin yordam chati**: To'lovlar, savol va takliflar uchun to'g'ridan-to'g'ri ma'muriyat bilan aloqa.

### 4. AB Games — So'z o'yinlari
- **Wordle, Anagram, Speed Match, Mistake Review**: So'z boyligini oshirish uchun qiziqarli o'yinlar moduli.
- O'yinlar orqali kunlik vazifalarni bajarish va darajani ko'tarish.

### 5. Boshqaruv paneli (Control Panel)
- **Maxsus boshqaruv interfeysi**: Standart Django adminidan tashqari maxsus optimallashtirilgan qulay dashboard.
- **Live Imtihon nazorati**: Jonli ravishda qaysi talaba qaysi testni ishlayotganini ko'rish.
- **Writing tekshirish stoli**: Administratorlar uchun insho matnini o'qish, mezonlar bo'yicha baholash va izoh yozish qulayligi.
- **Foydalanuvchilar va Guruhlar**: O'quvchilarni boshqarish, to'lovlarni tasdiqlash, guruhlarga taqsimlash.

### 6. Flutter mobil ilovasi
- `mobile/` papkasida iOS va Android uchun to'liq Flutter ilovasi.
- Web platforma bilan 100% sinxronlashgan API (`/api/learn/...`).
- Ovozni tanish (Speech-to-Text) va talaffuz (TTS) funksiyalari qurilmaning o'zida tezkor ishlaydi.

### 7. Telegram Bot integratsiyasi
- Yangi ro'yxatdan o'tishlar va tizimga kirishlar haqida adminlarga bildirishnoma.
- Imtihon natijalari e'lon qilinganda talabalarga shaxsiy Telegram xabarnomasi.

---

## 🛠 Texnologiyalar to'plami (Tech Stack)

| Yo'nalish | Texnologiyalar |
|---|---|
| **Backend** | Python 3.11+, Django 4.2 LTS, Gunicorn, WhiteNoise |
| **Baza** | PostgreSQL (Production) / SQLite (Development) |
| **Frontend** | Vanilla JS, HTML5, CSS3 Variables (Dark/Light mode), Lucide Icons |
| **Mobil ilova** | Flutter, Dart, Riverpod / Provider, Shared Preferences |
| **AI integratsiya** | OpenAI API (GPT-4o) |
| **Integratsiyalar** | Telegram Bot API, To'lov tizimlari (Payme / Click) |
| **Kesh & Xavfsizlik** | Django Cache, CSRF, Secure SSL, XSS-himoya, Rate-limiting |

---

## 📁 Loyiha tuzilishi

```text
abexam.uz/
├── Audio/                 # Tinglash (Listening) test audio fayllari
├── chat/                  # AbChat ijtimoiy xonalar va shaxsiy xabarlar ilovasi
├── core/                  # Asosiy sozlamalar, AI utilitlari, middleware va umumiy modellar
├── data/                  # Cambridge IELTS JSON formatidagi testlar bazasi
├── exams/                 # Imtihonlar, baholash, savollar va reyting moduli
├── games/                 # AB Games interaktiv so'z o'yinlari
├── learn/                 # A1–C2 ingliz tili o'quv kursi va mobil REST API
├── mobile/                # Flutter mobil ilovasi kodi
├── panel/                 # Maxsus ma'muriyat (Staff) boshqaruv paneli
├── payments/              # To'lovlar va AB Premium xizmati
├── static/                # CSS, JavaScript va rasmlar
├── templates/             # HTML shablonlar (Django templates)
├── tgbot/                 # Telegram bot boshqaruvi va vebxuklar
├── users/                 # Foydalanuvchilar, autentifikatsiya va profil
├── deploy.sh              # Serverga avtomatlashtirilgan deploy skripti
├── manage.py              # Django CLI boshqaruvchisi
├── passenger_wsgi.py      # cPanel / Eskiz hostingi uchun WSGI kirish nuqtasi
└── requirements.txt       # Python kutubxonalari ro'yxati
```

---

## 🚀 O'rnatish va mahalliy ishga tushirish

### 1. Repozitoriyani klonlash
```bash
git clone https://github.com/Iftix0r/abexam.uz.git
cd abexam.uz
```

### 2. Virtual muhit yaratish va kutubxonalarni o'rnatish
```bash
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. `.env` faylini sozlash
`.env.example` faylidan nusxa olib, `.env` faylini yarating:
```bash
cp .env.example .env
```
Fayl ichidagi `SECRET_KEY` va boshqa kerakli parametrlarni o'zgartiring.

### 4. Ma'lumotlar bazasi migratsiyalari va boshlang'ich ma'lumotlar
```bash
python manage.py migrate
python manage.py createsuperuser
# Cambridge testlarini bazaga yuklash (ixtiyoriy)
python manage.py seed_cambridge
```

### 5. Serverni ishga tushirish
```bash
python manage.py runserver
```
Brauzerda oching: [http://127.0.0.1:8000](http://127.0.0.1:8000)

### 6. Testlarni ishga tushirish
```bash
python manage.py test
```

---

## ⚙️ Muhit o'zgaruvchilari (.env)

| Parametr | Standart qiymat | Tavsif |
|---|---|---|
| `SECRET_KEY` | - | Django maxfiy kaliti (ishlab chiqarishda majburiy) |
| `DEBUG` | `False` | Debug rejimi (`True` yoki `False`) |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Ruxsat etilgan domenlar |
| `DB_NAME` | *(bo'sh)* | PostgreSQL baza nomi (bo'sh qolsa SQLite ishlatiladi) |
| `DB_USER` / `DB_PASSWORD` | - | PostgreSQL ulanish rekvizitlari |
| `DB_HOST` / `DB_PORT` | `127.0.0.1` / `5432` | Baza hosti va porti |
| `OPENAI_API_KEY` | - | Writing va "Explain answer" uchun OpenAI API kaliti |
| `TELEGRAM_BOT_TOKEN` | - | Admin va talabalar Telegram boti tokeni |
| `TELEGRAM_ADMIN_CHAT_ID` | - | Bildirishnomalar boruvchi admin chat IDsi |
| `SITE_URL` | `https://abexam.uz` | Saytning to'liq havolasi |

---

## 🚢 Serverga joylash (Deployment)

Loyiha cPanel / Eskiz.uz ("Python App" / Passenger) hamda Gunicorn + Nginx serverlarida ishlashga to'liq moslashtirilgan.

Serverda avtomatik yangilash uchun:
```bash
# Birinchi marta sozlash:
bash deploy.sh --init

# Keyingi yangilanishlar (kodni tortish, migratsiya, collectstatic, restart):
bash deploy.sh
```

---

## 👥 Muallif va Rivojlantirish

- **Muallif & Dasturchi**: [Iftixor To'ychiyev](https://github.com/Iftix0r)
- **Loyiha manzili**: [https://abexam.uz](https://abexam.uz)

---

<p align="center">
  O'zbekistonda zamonaviy ta'lim texnologiyalarini rivojlantirish yo'lida mehr bilan yaratilgan ❤️
</p>
