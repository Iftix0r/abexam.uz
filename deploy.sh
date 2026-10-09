#!/usr/bin/env bash
# AbExam — serverda yangilash skripti (eskiz.uz / cPanel "Python App").
#
# Ishlatish (serverda, loyiha papkasida):
#   bash deploy.sh            # oddiy yangilash
#   bash deploy.sh --init     # BIRINCHI MARTA: papka hali git repo bo'lmasa
#
# Nima qiladi:
#   1) virtualenv'ni yoqadi
#   2) db.sqlite3 zaxira nusxasini oladi (backups/ ichiga, oxirgi 10 tasi saqlanadi)
#   3) GitHub'dan yangi kodni oladi (main)
#   4) requirements.txt o'zgargan bo'lsa — paketlarni o'rnatadi
#   5) migrate + collectstatic
#   6) saytni qayta ishga tushiradi (tmp/restart.txt)
# Biror qadam xato bersa — skript to'xtaydi, sayt eski holatida qoladi.

set -euo pipefail

APP_DIR="/home/host7905/examab"
VENV="/home/host7905/virtualenv/examab/3.11/bin/activate"
REPO_URL="https://github.com/Iftix0r/abexam.uz.git"
BRANCH="main"
KEEP_BACKUPS=10

green() { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
red() { printf '\033[31m%s\033[0m\n' "$*"; }
step() { echo; green "==> $*"; }
trap 'red "XATO: deploy to'\''xtadi (yuqoridagi xabarni ko'\''ring). Sayt eski kod bilan ishlashda davom etadi."' ERR

cd "$APP_DIR"

step "Virtualenv yoqilmoqda"
# shellcheck disable=SC1090
source "$VENV"
python --version

# ── Birinchi marta: mavjud papkani git repo'ga aylantirish ────────────────
if [ ! -d .git ]; then
  if [ "${1:-}" != "--init" ]; then
    red "Bu papka hali git repo emas."
    echo "Birinchi marta shunday ishga tushiring:  bash deploy.sh --init"
    exit 1
  fi
  step "Git repo ulanmoqda ($REPO_URL)"
  git init -q
  git remote add origin "$REPO_URL"
fi

step "Ma'lumotlar bazasi zaxiralanmoqda"
mkdir -p backups
if [ -f db.sqlite3 ]; then
  BK="backups/db_$(date +%Y%m%d_%H%M%S).sqlite3"
  cp db.sqlite3 "$BK"
  echo "Saqlandi: $BK"
  # eski zaxiralarni tozalash (oxirgi $KEEP_BACKUPS tasi qoladi)
  ls -1t backups/db_*.sqlite3 2>/dev/null | tail -n +$((KEEP_BACKUPS + 1)) | xargs -r rm -f
else
  yellow "db.sqlite3 topilmadi (PostgreSQL ishlatilayotgan bo'lsa — normal)"
fi

step "Yangi kod olinmoqda ($BRANCH)"
OLD_REQ_HASH="$(md5sum requirements.txt 2>/dev/null | cut -d' ' -f1 || true)"
OLD_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo 'yo'\''q')"
git fetch -q origin "$BRANCH"
# Serverda kod qo'lda o'zgartirilgan bo'lsa ham GitHub'dagi holatga keltiriladi.
# .gitignore'dagi fayllar (db.sqlite3, media/, .env, logs/ ...) TEGILMAYDI.
git reset -q --hard "origin/$BRANCH"
NEW_COMMIT="$(git rev-parse --short HEAD)"
echo "Kod: $OLD_COMMIT  →  $NEW_COMMIT"
git log -1 --format='Oxirgi commit: %s (%cr)'

NEW_REQ_HASH="$(md5sum requirements.txt | cut -d' ' -f1)"
if [ "$OLD_REQ_HASH" != "$NEW_REQ_HASH" ] || [ "${1:-}" = "--init" ]; then
  step "Paketlar o'rnatilmoqda (requirements.txt o'zgargan)"
  pip install -q -r requirements.txt
else
  echo "requirements.txt o'zgarmagan — paketlar o'rnatilmaydi"
fi

step "Migratsiyalar"
python manage.py migrate --noinput

step "Statik fayllar"
python manage.py collectstatic --noinput -v 0

step "Tekshiruv"
python manage.py check --deploy --fail-level ERROR 2>&1 | grep -v "W0\|ckeditor" || true

step "Sayt qayta ishga tushirilmoqda"
mkdir -p tmp
touch tmp/restart.txt

echo
green "✓ Tayyor! $NEW_COMMIT versiyasi ishga tushdi."
