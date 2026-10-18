#!/usr/bin/env bash
# CF Control installer & manager — Developed by DenTeeR
# Usage:  curl -fsSL https://raw.githubusercontent.com/DenTeeR/CFManagement/main/install.sh | sudo bash
set -Eeuo pipefail

APP="CF Control"; DEV="DenTeeR"; VER="2.0"
REPO="${CFBOT_REPO:-DenTeeR/CFManagement}"; BRANCH="${CFBOT_BRANCH:-main}"
RAW="https://raw.githubusercontent.com/${REPO}/${BRANCH}"
DIR="/opt/cfbot"; ENVF="/etc/cfbot.env"; SVC="cfbot"; SVCUSER="cfbot"
UNIT="/etc/systemd/system/${SVC}.service"; BIN="/usr/local/bin/cfbot"; LOG="/tmp/cfbot-install.log"
SELF="${BASH_SOURCE[0]:-$0}"
HAVE_SELF=0; [ -f "$SELF" ] && grep -q "CF Control installer" "$SELF" 2>/dev/null && HAVE_SELF=1
STEP=0; TOTAL=0; BOT_USERNAME=""

# ───────────────────────── UI ─────────────────────────
fg() { printf '\033[38;5;%sm' "$1"; }
R=$'\033[0m'; BD=$'\033[1m'
ACC=$(fg 117); PUR=$(fg 141); GRN=$(fg 84); RED=$(fg 203); YEL=$(fg 221); DIM=$(fg 245)

banner() {
  clear 2>/dev/null || true
  local cols; cols=$(tput cols 2>/dev/null || echo 80)
  echo
  if [ "$cols" -ge 62 ]; then
    local i=0 g=(93 99 105 111 117 123) line
    while IFS= read -r line; do
      printf '  %s%s%s\n' "$(fg "${g[$i]}")" "$line" "$R"; i=$((i + 1))
    done <<'ART'
██████╗ ███████╗███╗   ██╗████████╗███████╗███████╗██████╗
██╔══██╗██╔════╝████╗  ██║╚══██╔══╝██╔════╝██╔════╝██╔══██╗
██║  ██║█████╗  ██╔██╗ ██║   ██║   █████╗  █████╗  ██████╔╝
██║  ██║██╔══╝  ██║╚██╗██║   ██║   ██╔══╝  ██╔══╝  ██╔══██╗
██████╔╝███████╗██║ ╚████║   ██║   ███████╗███████╗██║  ██║
╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚══════╝╚══════╝╚═╝  ╚═╝
ART
  else
    printf '  %s%s◆ D e n T e e R%s\n' "$BD" "$PUR" "$R"
  fi
  printf '\n  %s☁  %s%s%s  %s·  v%s  ·  Cloudflare control inside Telegram%s\n' "$ACC" "$BD" "$APP" "$R$DIM" "" "$VER" "$R"
  printf '  %s%s%s\n\n' "$DIM" "────────────────────────────────────────────────────────" "$R"
}

ok()   { printf '  %s✔%s %s\n' "$GRN" "$R" "$*"; }
warn() { printf '  %s!%s %s\n' "$YEL" "$R" "$*"; }
die()  { printf '  %s✘%s %s\n' "$RED" "$R" "$*" >&2; exit 1; }
section() { printf '\n  %s%s▌ %s%s\n\n' "$BD" "$PUR" "$*" "$R"; }

box() {  # box "line" ... (ASCII only inside, colors allowed)
  local w=0 l p
  for l in "$@"; do p=$(printf '%s' "$l" | sed $'s/\033\\[[0-9;]*m//g'); [ ${#p} -gt $w ] && w=${#p}; done
  printf '  %s╭%s╮%s\n' "$PUR" "$(printf '─%.0s' $(seq 1 $((w + 2))))" "$R"
  for l in "$@"; do
    p=$(printf '%s' "$l" | sed $'s/\033\\[[0-9;]*m//g')
    printf '  %s│%s %s%*s %s│%s\n' "$PUR" "$R" "$l" $((w - ${#p})) "" "$PUR" "$R"
  done
  printf '  %s╰%s╯%s\n' "$PUR" "$(printf '─%.0s' $(seq 1 $((w + 2))))" "$R"
}

ask() {  # ask "prompt" VAR
  local v; read -rp "$(printf '  %s›%s %s: ' "$ACC" "$R" "$1")" v </dev/tty
  printf -v "$2" '%s' "$v"
}
confirm() {  # confirm "question" -> 0 yes
  local v; read -rp "$(printf '  %s?%s %s %s[y/N]%s ' "$YEL" "$R" "$1" "$DIM" "$R")" v </dev/tty; [[ "$v" =~ ^[Yy]$ ]]
}
pause() { local _; read -rp "$(printf '\n  %sPress Enter to continue…%s' "$DIM" "$R")" _ </dev/tty || true; }

run() {  # run "message" command...   (spinner + log)
  local msg="$1"; shift; STEP=$((STEP + 1))
  "$@" >>"$LOG" 2>&1 </dev/null &
  local pid=$! i=0 sp=(⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏)
  tput civis 2>/dev/null || true
  while kill -0 "$pid" 2>/dev/null; do
    printf '\r  %s%s%s %s[%d/%d]%s %s' "$ACC" "${sp[$((i % 10))]}" "$R" "$DIM" "$STEP" "$TOTAL" "$R" "$msg"
    i=$((i + 1)); sleep 0.1
  done
  tput cnorm 2>/dev/null || true
  if wait "$pid"; then
    printf '\r\033[2K  %s✔%s %s[%d/%d]%s %s\n' "$GRN" "$R" "$DIM" "$STEP" "$TOTAL" "$R" "$msg"
  else
    printf '\r\033[2K  %s✘%s %s[%d/%d]%s %s\n\n' "$RED" "$R" "$DIM" "$STEP" "$TOTAL" "$R" "$msg"
    tail -n 12 "$LOG" | sed 's/^/    /'; die "Failed. Full log: $LOG"
  fi
}

need_root() {
  [ "$(id -u)" -eq 0 ] && return 0
  if [ "$HAVE_SELF" -eq 1 ] && command -v sudo >/dev/null; then exec sudo -E bash "$SELF" "$@"; fi
  die "Please run as root:  curl -fsSL $RAW/install.sh | sudo bash"
}

# ───────────────────────── steps ─────────────────────────
s_apt()   { export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a; apt-get update -y; apt-get install -y python3 python3-venv python3-pip curl ca-certificates; }
s_user()  { id "$SVCUSER" >/dev/null 2>&1 || useradd --system --home "$DIR" --shell /usr/sbin/nologin "$SVCUSER"; mkdir -p "$DIR"; }
s_files() {
  local src; src="$(dirname "$SELF")/cfbot.py"
  if [ "$HAVE_SELF" -eq 1 ] && [ -f "$src" ]; then cp "$src" "$DIR/cfbot.py"; else curl -fsSL "$RAW/cfbot.py" -o "$DIR/cfbot.py"; fi
  chown -R "$SVCUSER:$SVCUSER" "$DIR"
}
s_venv()  { python3 -m venv "$DIR/venv"; "$DIR/venv/bin/pip" install -q --upgrade pip httpx; chown -R "$SVCUSER:$SVCUSER" "$DIR"; }
s_service() {
  cat >"$UNIT" <<EOF
[Unit]
Description=CF Control (Cloudflare Telegram bot) - by DenTeeR
After=network-online.target
Wants=network-online.target

[Service]
User=$SVCUSER
WorkingDirectory=$DIR
EnvironmentFile=$ENVF
ExecStart=$DIR/venv/bin/python $DIR/cfbot.py
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$DIR

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload; systemctl enable "$SVC"
}
s_cli() {
  if [ "$HAVE_SELF" -eq 1 ] && [ "$SELF" -ef "$BIN" ]; then return 0; fi
  if [ "$HAVE_SELF" -eq 1 ]; then install -m 755 "$SELF" "$BIN"; else curl -fsSL "$RAW/install.sh" -o "$BIN" && chmod 755 "$BIN"; fi
}
s_start() { systemctl restart "$SVC"; sleep 3; systemctl is-active --quiet "$SVC"; }
s_update() {
  curl -fsSL "$RAW/cfbot.py" -o "$DIR/cfbot.py.new"
  python3 -c "import ast,sys; ast.parse(open(sys.argv[1], encoding='utf-8').read())" "$DIR/cfbot.py.new"
  [ -f "$DIR/cfbot.py" ] && cp "$DIR/cfbot.py" "$DIR/cfbot.py.bak"
  mv "$DIR/cfbot.py.new" "$DIR/cfbot.py"; chown -R "$SVCUSER:$SVCUSER" "$DIR"
  curl -fsSL "$RAW/install.sh" -o "$BIN.new" && chmod 755 "$BIN.new" && mv "$BIN.new" "$BIN" || true
}

# ───────────────────────── config ─────────────────────────
check_token() { BOT_USERNAME=$(curl -fsS "https://api.telegram.org/bot$1/getMe" 2>/dev/null | grep -o '"username":"[^"]*"' | cut -d'"' -f4 || true); [ -n "$BOT_USERNAME" ]; }

configure() {
  if [ -z "${BOT_TOKEN:-}" ] || [ -z "${ADMIN_IDS:-}" ]; then
    [ -r /dev/tty ] || die "No terminal. Pass BOT_TOKEN and ADMIN_IDS as environment variables."
    section "Configuration"
    local n=0
    while :; do
      ask "Bot token (from @BotFather)" BOT_TOKEN
      if check_token "$BOT_TOKEN"; then ok "Token valid  →  @$BOT_USERNAME"; break; fi
      warn "Invalid token or no connection. Try again."; n=$((n + 1)); [ $n -ge 3 ] && die "Too many invalid attempts."
    done
    while :; do
      ask "Admin numeric ID(s), comma separated (from @userinfobot)" ADMIN_IDS
      [[ "$ADMIN_IDS" =~ ^[0-9]+(,[0-9]+)*$ ]] && break
      warn "Numbers only, e.g.  123456789,987654321"
    done
  else
    check_token "$BOT_TOKEN" || die "BOT_TOKEN is invalid."
    [[ "$ADMIN_IDS" =~ ^[0-9]+(,[0-9]+)*$ ]] || die "ADMIN_IDS is invalid."
  fi
}
write_env() { ( umask 077; printf 'BOT_TOKEN=%s\nADMIN_IDS=%s\n' "$BOT_TOKEN" "$ADMIN_IDS" >"$ENVF" ); chmod 600 "$ENVF"; }

# ───────────────────────── commands ─────────────────────────
do_install() {
  need_root install; : >"$LOG"; banner
  command -v apt-get >/dev/null || die "This installer supports Ubuntu / Debian (apt)."
  ok "System: $(. /etc/os-release && echo "$PRETTY_NAME")"
  if [ -f "$ENVF" ] && [ -z "${BOT_TOKEN:-}" ] && [ -r /dev/tty ]; then
    confirm "Existing config found. Keep it?" && { set -a; . "$ENVF"; set +a; check_token "$BOT_TOKEN" || true; } || { BOT_TOKEN=""; ADMIN_IDS=""; }
  fi
  [ -n "${BOT_TOKEN:-}" ] || configure
  [ -n "${BOT_USERNAME:-}" ] || check_token "$BOT_TOKEN" || true
  write_env
  section "Installing"
  TOTAL=7; STEP=0
  run "Installing system packages"      s_apt
  run "Creating service user"           s_user
  run "Deploying bot files"             s_files
  run "Building Python environment"     s_venv
  run "Registering systemd service"     s_service
  run "Installing 'cfbot' manager"      s_cli
  run "Starting the bot"                s_start
  echo
  box "${BD}${GRN}Installation complete!${R}" "" \
      "Bot       : @${BOT_USERNAME:-your-bot}" "Admins    : $ADMIN_IDS" \
      "Manage    : ${ACC}cfbot${R}   (menu: status/logs/update)" "Config    : $ENVF" "Data      : $DIR/data.json" "" \
      "Now open Telegram and send ${ACC}/start${R} to your bot."
  printf '\n  %sDeveloped with ♥ by %s%s%s\n\n' "$DIM" "$BD$PUR" "$DEV" "$R"
}

status_line() {
  if systemctl is-active --quiet "$SVC" 2>/dev/null; then printf '  %s●%s %sRunning%s' "$GRN" "$R" "$BD" "$R"; else printf '  %s●%s %sStopped%s' "$RED" "$R" "$BD" "$R"; fi
  [ -f "$ENVF" ] && printf '   %s·  admins: %s%s' "$DIM" "$(grep '^ADMIN_IDS=' "$ENVF" | cut -d= -f2)" "$R"; echo
}

do_update() { need_root update; : >"$LOG"; TOTAL=2; STEP=0; run "Fetching latest version" s_update; run "Restarting the bot" s_start; ok "Updated."; }
do_config() {
  need_root config; BOT_TOKEN=""; ADMIN_IDS=""; banner; configure; write_env
  TOTAL=1; STEP=0; : >"$LOG"; run "Restarting the bot" s_start
}
do_logs() { need_root logs; if [ "${1:-}" = "-f" ]; then ( trap 'exit 0' INT; journalctl -u "$SVC" -f -o cat ); else journalctl -u "$SVC" -n 50 --no-pager -o cat; fi; }
do_uninstall() {
  need_root uninstall
  confirm "Remove CF Control completely?" || { warn "Cancelled."; return 0; }
  local keep=0; confirm "Keep your data (accounts / design) in a backup?" && keep=1
  [ "$keep" -eq 1 ] && [ -f "$DIR/data.json" ] && { cp "$DIR/data.json" "/root/cfbot-data-backup.json"; ok "Backup: /root/cfbot-data-backup.json"; }
  systemctl disable --now "$SVC" 2>/dev/null || true
  rm -rf "$UNIT" "$DIR" "$ENVF"; systemctl daemon-reload
  userdel "$SVCUSER" 2>/dev/null || true
  ok "Removed. Bye!"; rm -f "$BIN"
}

do_menu() {
  need_root menu
  while :; do
    banner; status_line; echo
    printf '  %s1%s  Status          %s5%s  Change token / admins\n' "$ACC" "$R" "$ACC" "$R"
    printf '  %s2%s  Logs            %s6%s  Uninstall\n' "$ACC" "$R" "$ACC" "$R"
    printf '  %s3%s  Restart         %s0%s  Exit\n' "$ACC" "$R" "$ACC" "$R"
    printf '  %s4%s  Update\n\n' "$ACC" "$R"
    local c; read -rp "$(printf '  %s›%s Choose: ' "$ACC" "$R")" c </dev/tty || exit 0
    case "$c" in
      1) systemctl status "$SVC" --no-pager -l | head -n 14; pause ;;
      2) do_logs; pause ;;
      3) TOTAL=1; STEP=0; : >"$LOG"; run "Restarting the bot" s_start; pause ;;
      4) do_update; pause ;;
      5) do_config; pause ;;
      6) do_uninstall; pause; [ -f "$UNIT" ] || exit 0 ;;
      0|q) echo; exit 0 ;;
    esac
  done
}

usage() { cat <<EOF
$APP v$VER — by $DEV
  cfbot            open the manager menu (or install if missing)
  cfbot install    (re)install        cfbot update     update to latest
  cfbot status     service status     cfbot logs [-f]  show / follow logs
  cfbot restart    restart the bot    cfbot config     change token / admins
  cfbot uninstall  remove everything
EOF
}

case "${1:-}" in
  install)   do_install ;;
  update)    do_update ;;
  config)    do_config ;;
  logs)      do_logs "${2:-}" ;;
  status)    systemctl status "$SVC" --no-pager -l ;;
  restart)   need_root restart; systemctl restart "$SVC" && echo "restarted" ;;
  uninstall) do_uninstall ;;
  menu)      do_menu ;;
  -h|--help|help) usage ;;
  "")        if [ -f "$UNIT" ]; then do_menu; else do_install; fi ;;
  *)         usage; exit 1 ;;
esac
