#!/usr/bin/env bash
# AbExam production deployment — cPanel / Passenger.
#   bash deploy.sh          oddiy yangilash
#   bash deploy.sh --init   birinchi o'rnatish

set -euo pipefail

APP_DIR="/home/host7905/examab"
VENV="/home/host7905/virtualenv/examab/3.11/bin/activate"
REPO_URL="https://github.com/Iftix0r/abexam.uz.git"
BRANCH="main"
KEEP_BACKUPS=10
DEPLOY_STARTED=$SECONDS
STEP_NO=0
TOTAL_STEPS=8

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  RESET='\033[0m'; BOLD='\033[1m'; DIM='\033[2m'
  RED='\033[38;5;196m'; GREEN='\033[38;5;46m'; YELLOW='\033[38;5;220m'
  BLUE='\033[38;5;39m'; GRAY='\033[38;5;245m'; WHITE='\033[38;5;255m'
else
  RESET=''; BOLD=''; DIM=''; RED=''; GREEN=''; YELLOW=''; BLUE=''; GRAY=''; WHITE=''
fi

line() { printf "${GRAY}────────────────────────────────────────────────────────────${RESET}\n"; }
info() { printf "  ${BLUE}●${RESET} %s\n" "$*"; }
ok() { printf "  ${GREEN}✓${RESET} %s\n" "$*"; }
warn() { printf "  ${YELLOW}▲${RESET} %s\n" "$*"; }
fail() { printf "  ${RED}✕${RESET} %s\n" "$*"; }
step() {
  STEP_NO=$((STEP_NO + 1))
  printf "\n${BOLD}${WHITE}[%02d/%02d]${RESET} ${BOLD}%s${RESET}\n" "$STEP_NO" "$TOTAL_STEPS" "$*"
}
elapsed() {
  local total=$((SECONDS - DEPLOY_STARTED))
  printf '%dm %02ds' $((total / 60)) $((total % 60))
}
on_error() {
  local code=$?
  echo
  line
  fail "Deploy ${STEP_NO}-bosqichda to'xtadi (xato kodi: ${code})"
  printf "  ${DIM}Sayt oldingi ishlayotgan versiyada qoldi · Vaqt: %s${RESET}\n" "$(elapsed)"
  line
  exit "$code"
}
trap on_error ERR

printf "\n${RED}${BOLD}   █████╗ ██████╗ ${RESET} ${WHITE}${BOLD}███████╗██╗  ██╗ █████╗ ███╗   ███╗${RESET}\n"
printf "${RED}${BOLD}  ██╔══██╗██╔══██╗${RESET} ${WHITE}${BOLD}██╔════╝╚██╗██╔╝██╔══██╗████╗ ████║${RESET}\n"
printf "${RED}${BOLD}  ███████║██████╔╝${RESET} ${WHITE}${BOLD}█████╗   ╚███╔╝ ███████║██╔████╔██║${RESET}\n"
printf "${RED}${BOLD}  ██╔══██║██╔══██╗${RESET} ${WHITE}${BOLD}██╔══╝   ██╔██╗ ██╔══██║██║╚██╔╝██║${RESET}\n"
printf "${RED}${BOLD}  ██║  ██║██████╔╝${RESET} ${WHITE}${BOLD}███████╗██╔╝ ██╗██║  ██║██║ ╚═╝ ██║${RESET}\n"
printf "${RED}${BOLD}  ╚═╝  ╚═╝╚═════╝ ${RESET} ${WHITE}${BOLD}╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝${RESET}\n"
printf "\n  ${DIM}Production deployment · %s · branch: %s${RESET}\n" "$(date '+%d.%m.%Y %H:%M:%S')" "$BRANCH"
line

cd "$APP_DIR"

step "Virtualenv tayyorlanmoqda"
# shellcheck disable=SC1090
source "$VENV"
ok "$(python --version) · virtualenv faol"

if [ ! -d .git ]; then
  if [ "${1:-}" != "--init" ]; then
    fail "Bu papka hali Git repository emas"
    info "Birinchi marta: bash deploy.sh --init"
    exit 1
  fi
  info "Git repository ulanmoqda: $REPO_URL"
  git init -q
  git remote add origin "$REPO_URL"
fi

step "Ma'lumotlar bazasi zaxiralanmoqda"
mkdir -p backups
if [ -f db.sqlite3 ]; then
  BK="backups/db_$(date +%Y%m%d_%H%M%S).sqlite3"
  cp db.sqlite3 "$BK"
  ok "Zaxira saqlandi: $BK"
  ls -1t backups/db_*.sqlite3 2>/dev/null | tail -n +$((KEEP_BACKUPS + 1)) | xargs -r rm -f
else
  warn "db.sqlite3 topilmadi (PostgreSQL ishlatilsa bu normal)"
fi

step "Yangi kod olinmoqda"
OLD_REQ_HASH="$(md5sum requirements.txt 2>/dev/null | cut -d' ' -f1 || true)"
OLD_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo 'yo'\''q')"
git fetch -q origin "$BRANCH"
git reset -q --hard "origin/$BRANCH"
NEW_COMMIT="$(git rev-parse --short HEAD)"
ok "Versiya: $OLD_COMMIT → $NEW_COMMIT"
info "$(git log -1 --format='%s · %cr')"

step "Python paketlari tekshirilmoqda"
NEW_REQ_HASH="$(md5sum requirements.txt | cut -d' ' -f1)"
if [ "$OLD_REQ_HASH" != "$NEW_REQ_HASH" ] || [ "${1:-}" = "--init" ]; then
  info "requirements.txt o'zgargan — paketlar yangilanmoqda"
  pip install -q -r requirements.txt
  ok "Paketlar o'rnatildi"
else
  ok "Paketlar o'zgarmagan"
fi

step "Migratsiyalar qo'llanmoqda"
python manage.py migrate --noinput
python manage.py migrate --check
ok "Ma'lumotlar bazasi sxemasi tayyor"

step "Statik fayllar yig'ilmoqda"
python manage.py collectstatic --noinput -v 0
ok "Statik fayllar tayyor"

step "Xavfsizlik va tizim tekshiruvi"
python manage.py check --deploy --fail-level ERROR
ok "Django production tekshiruvi o'tdi"

step "Sayt qayta ishga tushirilmoqda"
mkdir -p tmp
touch tmp/restart.txt
ok "Passenger restart signali yuborildi"

echo
line
printf "  ${GREEN}${BOLD}✓ DEPLOY MUVAFFAQIYATLI${RESET}\n"
printf "  ${WHITE}Versiya${RESET}  ${BOLD}%s${RESET}\n" "$NEW_COMMIT"
printf "  ${WHITE}Branch${RESET}   %s\n" "$BRANCH"
printf "  ${WHITE}Vaqt${RESET}     %s\n" "$(elapsed)"
printf "  ${WHITE}Holat${RESET}    ${GREEN}● AbExam ishga tushdi${RESET}\n"
line
echo
