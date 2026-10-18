#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"

find_python_bin() {
  for candidate in python py python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c "import sys; print(sys.executable)" >/dev/null 2>&1; then
        printf '%s\n' "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

usage() {
  cat <<'EOF'
Usage:
  ./script/start.sh [--check]

Validates the Naukri setup, optionally validates Discord config, and starts
the scheduler + bot if they are configured.
EOF
}

CHECK_ONLY=0

for arg in "$@"; do
  case "$arg" in
    --check) CHECK_ONLY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; usage >&2; exit 1 ;;
  esac
done

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing .env. Run the setup script first." >&2
  exit 1
fi

if ! PYTHON_BIN="$(find_python_bin)"; then
  echo "Python 3 is required for validation." >&2
  exit 1
fi

echo "==> Validating Naukri configuration"
"$PYTHON_BIN" - "$ENV_FILE" <<'PY'
import pathlib
import sys

env_path = pathlib.Path(sys.argv[1])
env = {}
for line in env_path.read_text(encoding="utf-8").splitlines():
    if "=" not in line or line.strip().startswith("#"):
        continue
    key, value = line.split("=", 1)
    env[key.strip()] = value.strip().strip("'\"")

required = ["INPUT_USERNAME", "INPUT_PASSWORD", "INPUT_PROFILE_ID"]
missing = [key for key in required if not env.get(key, "").strip()]

if missing:
    print("Missing required Naukri values:", ", ".join(missing), file=sys.stderr)
    raise SystemExit(1)

resume_path = env.get("INPUT_RESUME_PATH", "").strip()
if resume_path:
    p = pathlib.Path(resume_path).expanduser()
    if not p.exists():
        print(f"Warning: INPUT_RESUME_PATH does not exist: {p}")
else:
    print("Warning: INPUT_RESUME_PATH is blank; resume uploads will fail until it is set.")

webhook = env.get("DISCORD_WEBHOOK_URL", "").strip()
bot_token = env.get("DISCORD_BOT_TOKEN", "").strip()
owner_id = env.get("DISCORD_USER_ID", "").strip()
guild_id = env.get("DISCORD_GUILD_ID", "").strip()

if webhook:
    print("Discord webhook: configured")
else:
    print("Discord webhook: not configured (optional)")

if bot_token and owner_id and guild_id:
    print("Discord bot: ready")
elif bot_token or owner_id or guild_id:
    print("Discord bot: partially configured; missing one or more of DISCORD_BOT_TOKEN, DISCORD_USER_ID, DISCORD_GUILD_ID")
else:
    print("Discord bot: not configured (optional)")

print("Naukri config: OK")
PY

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  echo "Validation passed. Nothing started."
  exit 0
fi

echo "==> Generating scheduler jobs"
"$PYTHON_BIN" "$ROOT_DIR/scheduler/scheduler.py" generate

BOT_READY="$("$PYTHON_BIN" - "$ENV_FILE" <<'PY'
import pathlib
import sys

env_path = pathlib.Path(sys.argv[1])
env = {}
for line in env_path.read_text(encoding="utf-8").splitlines():
    if "=" not in line or line.strip().startswith("#"):
        continue
    key, value = line.split("=", 1)
    env[key.strip()] = value.strip().strip("'\"")

token = env.get("DISCORD_BOT_TOKEN", "").strip()
user_id = env.get("DISCORD_USER_ID", "").strip()
guild_id = env.get("DISCORD_GUILD_ID", "").strip()

if token and user_id and guild_id:
    print("ready")
else:
    print("skip")
PY
)"

if [[ "$BOT_READY" == "ready" ]]; then
  SERVICE_NAME="naukri-discord-bot.service"
  if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    echo "==> Restarting Discord bot service"
    if sudo systemctl restart "$SERVICE_NAME"; then
      echo "Discord bot started successfully."
    else
      echo "Discord bot not started because the service restart failed."
    fi
  else
    echo "==> Starting Discord bot service"
    if sudo systemctl start "$SERVICE_NAME"; then
      echo "Discord bot started successfully."
    else
      echo "Discord bot not started because the service start failed."
    fi
  fi

  echo "==> Service status"
  sudo systemctl status "$SERVICE_NAME" --no-pager || true

  echo "==> Recent service logs"
  sudo journalctl -u "$SERVICE_NAME" -n 60 --no-pager || true
else
  echo "Discord bot not started because DISCORD_BOT_TOKEN, DISCORD_USER_ID, and DISCORD_GUILD_ID are not all configured."
fi

echo

echo "Everything is configured."
echo "The scheduler is active. The Discord bot remains optional unless all required bot keys are present."
