#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
ENV_EXAMPLE="$ROOT_DIR/.env.example"

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
  ./script/setup.sh [--skip-env] [--no-install]

Creates the project environment, installs dependencies, creates a .env file,
and optionally walks the user through filling in credentials.
EOF
}

SKIP_ENV=0
NO_INSTALL=0

for arg in "$@"; do
  case "$arg" in
    --skip-env) SKIP_ENV=1 ;;
    --no-install) NO_INSTALL=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; usage >&2; exit 1 ;;
  esac
done

echo "==> Checking prerequisites"

if ! command -v node >/dev/null 2>&1; then
  echo "Node.js is required. Install it first." >&2
  exit 1
fi

if ! command -v yarn >/dev/null 2>&1; then
  echo "Yarn is required. Installing it now with npm..."
  sudo npm install -g yarn
fi

if ! PYTHON_BIN="$(find_python_bin)"; then
  echo "Python 3 is required to run the Discord bot." >&2
  exit 1
fi

if [[ "$NO_INSTALL" -eq 0 ]]; then
  echo "==> Installing Node dependencies"
  (cd "$ROOT_DIR" && yarn install --frozen-lockfile)

  echo "==> Building the action bundle"
  (cd "$ROOT_DIR" && yarn package)
fi

echo "==> Preparing the Discord bot virtual environment"
if [[ ! -d "$ROOT_DIR/bot/venv" ]]; then
  "$PYTHON_BIN" -m venv "$ROOT_DIR/bot/venv"
fi

if [[ -f "$ROOT_DIR/bot/venv/Scripts/python.exe" ]]; then
  VENV_PY="$ROOT_DIR/bot/venv/Scripts/python.exe"
else
  VENV_PY="$ROOT_DIR/bot/venv/bin/python"
fi

"$VENV_PY" -m pip install --upgrade pip
"$VENV_PY" -m pip install -r "$ROOT_DIR/bot/requirements.txt"

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  echo "Created $ENV_FILE from the example file."
fi

if [[ "$SKIP_ENV" -eq 1 ]]; then
  echo "Skipping .env prompts. Edit $ENV_FILE manually and then run the start script."
  exit 0
fi

read -r -p "Fill in .env values now? [Y/n] " answer
case "$answer" in
  n|N|no|NO)
    echo "OK — edit $ENV_FILE yourself, then run the start script."
    exit 0
    ;;
esac

"$PYTHON_BIN" - "$ENV_FILE" "$ENV_EXAMPLE" <<'PY'
import getpass
import pathlib
import sys

env_file = pathlib.Path(sys.argv[1])
example = pathlib.Path(sys.argv[2])

fields = [
    ("INPUT_USERNAME", "Naukri login email (required)", True),
    ("INPUT_PASSWORD", "Naukri password (required, hidden)", True),
    ("INPUT_PROFILE_ID", "Naukri profile ID (required)", True),
    ("INPUT_RESUME_HEADLINE", "Default headline (optional)", False),
    ("INPUT_RESUME_PATH", "Resume PDF path (optional but recommended)", False),
    ("DISCORD_WEBHOOK_URL", "Discord webhook URL (optional)", False),
    ("DISCORD_BOT_TOKEN", "Discord bot token (optional)", False),
    ("DISCORD_USER_ID", "Discord user ID (optional)", False),
    ("DISCORD_GUILD_ID", "Discord guild/server ID (optional)", False),
]

existing = {}
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        existing[key.strip()] = value.strip()

if not env_file.exists():
    env_file.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")

for key, label, required in fields:
    current = existing.get(key, "")
    if key in {"INPUT_PASSWORD", "DISCORD_BOT_TOKEN"}:
        if current:
            print(f"{label} [already set]")
        value = getpass.getpass(f"{label}: ").strip()
        if not value:
            value = current
    else:
        if current:
            print(f"{label} [current: {current}]")
        value = input(f"{label}: ").strip()
        if not value:
            value = current
    existing[key] = value

lines = []
seen = set()
for line in env_file.read_text(encoding="utf-8").splitlines():
    if "=" not in line or line.strip().startswith("#"):
        lines.append(line)
        continue

    key = line.split("=", 1)[0].strip()
    if key in existing:
        lines.append(f"{key}={existing[key]}")
        seen.add(key)
    else:
        lines.append(line)

for key, _, _ in fields:
    if key not in seen:
        lines.append(f"{key}={existing.get(key, '')}")

env_file.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
print(f"\nSaved values to {env_file}")
print("Keep this file private and do not commit it.")
PY

chmod 600 "$ENV_FILE" 2>/dev/null || true

echo

echo "Setup complete."
echo "Next: run the start script."
