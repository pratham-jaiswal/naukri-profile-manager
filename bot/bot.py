#!/usr/bin/env python3

import asyncio
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

ROOT = Path(__file__).resolve().parent.parent
BOT_DIR = ROOT / "bot"
ENV_FILE = ROOT / ".env"
SCHEDULER_FILE = ROOT / "scheduler" / "scheduler.py"
STATE_FILE = ROOT / "scheduler" / "today.json"
RESUME_DIR = Path.home() / "naukri-data" / "resumes"
MAX_PDF_SIZE = 10 * 1024 * 1024

sys.path.insert(0, str(ROOT))
from scheduler.scheduler import (
    load_env,
    manual_update,
    notify,
    local_now,
    local_timezone_name,
    parse_windows_json,
    update_config,
)


def set_env_value(key, value):
    """Update one .env key without rewriting unrelated credentials."""
    if "\n" in value or "\r" in value:
        raise ValueError("Newlines are not allowed in configuration values.")

    lines = ENV_FILE.read_text().splitlines()
    output = []
    found = False

    for line in lines:
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            existing_key = line.split("=", 1)[0].strip()
            if existing_key == key:
                if not found:
                    output.append(f"{key}='{value}'")
                    found = True
                continue
        output.append(line)

    if not found:
        output.append(f"{key}='{value}'")

    temp = ENV_FILE.with_suffix(".env.tmp")
    temp.write_text("\n".join(output) + "\n")
    os.chmod(temp, 0o600)
    os.replace(temp, ENV_FILE)
    os.chmod(ENV_FILE, 0o600)


def active_resume_path():
    value = load_env().get("INPUT_RESUME_PATH", "").strip()
    paths = [
        line.strip()
        for line in value.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return Path(paths[0]).expanduser() if paths else None


def resume_files():
    RESUME_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(
        RESUME_DIR.glob("*.pdf"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def archive_old_resumes(active_target):
    """Archive existing PDFs before saving the latest canonical resume."""
    import re

    RESUME_DIR.mkdir(parents=True, exist_ok=True)
    target = active_target.resolve()
    prefix_pattern = re.compile(r"^\d{8}-\d{6}-")

    for old in list(RESUME_DIR.glob("*.pdf")):
        if not old.is_file() or old.resolve() == target:
            continue

        # Already archived by a previous upload: preserve its original timestamp.
        if prefix_pattern.match(old.name):
            continue

        # ctime reflects when the file was created/copied onto this Linux VM.
        stamp = datetime.fromtimestamp(old.stat().st_ctime).strftime("%Y%m%d-%H%M%S")

        destination = RESUME_DIR / f"{stamp}-{old.name}"
        suffix = 2
        while destination.exists():
            destination = RESUME_DIR / f"{stamp}-{suffix}-{old.name}"
            suffix += 1

        old.rename(destination)
        print(f"Archived old resume as {destination.name}")


def read_state():
    if not STATE_FILE.exists():
        return None
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return None


class NaukriBot(commands.Bot):
    async def setup_hook(self):
        guild = discord.Object(id=int(load_env()["DISCORD_GUILD_ID"]))
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        print(f"Synced {len(synced)} guild slash commands.")


intents = discord.Intents.none()
bot = NaukriBot(command_prefix="!", intents=intents)


def authorized(interaction: discord.Interaction) -> bool:
    cfg = load_env()
    try:
        owner_id = int(cfg["DISCORD_USER_ID"])
        guild_id = int(cfg["DISCORD_GUILD_ID"])
    except (KeyError, ValueError):
        return False

    return (
        interaction.user.id == owner_id
        and interaction.guild_id == guild_id
    )


async def require_owner(interaction: discord.Interaction) -> bool:
    if authorized(interaction):
        return True

    message = "You are not authorized to control this bot."
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)
    return False


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}.")
    print("Naukri Bot is ready.")


@bot.tree.command(name="run", description="Run a Naukri update immediately")
@app_commands.choices(action=[
    app_commands.Choice(name="Headline", value="headline"),
    app_commands.Choice(name="Resume", value="resume"),
    app_commands.Choice(name="Both", value="both"),
])
async def run_command(
    interaction: discord.Interaction,
    action: app_commands.Choice[str],
):
    if not await require_owner(interaction):
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    result = await asyncio.to_thread(manual_update, action.value)
    prefix = "✅" if result["ok"] else ("⏳" if result["busy"] else "❌")
    await interaction.followup.send(
        f"{prefix} {result['message']}", ephemeral=True
    )


@bot.tree.command(name="headline", description="Set the saved Naukri resume headline")
@app_commands.describe(text="New headline, maximum 250 characters")
async def headline_command(interaction: discord.Interaction, text: str):
    if not await require_owner(interaction):
        return

    text = text.strip()
    if not text or len(text) > 250:
        await interaction.response.send_message(
            "Headline must contain 1–250 characters.", ephemeral=True
        )
        return

    set_env_value("INPUT_RESUME_HEADLINE", text)
    await interaction.response.send_message(
        "✅ Headline saved. It will be used on the next headline update; "
        "use `/run` with Headline to apply it immediately.",
        ephemeral=True,
    )


@bot.tree.command(name="resume_upload", description="Upload and activate a resume PDF")
@app_commands.describe(file="PDF to save as your active resume")
async def resume_upload_command(
    interaction: discord.Interaction,
    file: discord.Attachment,
):
    if not await require_owner(interaction):
        return

    if not file.filename.lower().endswith(".pdf"):
        await interaction.response.send_message(
            "Please attach a PDF file.", ephemeral=True
        )
        return

    if file.size > MAX_PDF_SIZE:
        await interaction.response.send_message(
            "PDF is too large. Maximum supported size is 10 MiB.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    try:
        content = await file.read()
        if len(content) > MAX_PDF_SIZE or not content.startswith(b"%PDF-"):
            await interaction.followup.send(
                "❌ The attachment doesn't appear to be a valid PDF.",
                ephemeral=True,
            )
            return

        RESUME_DIR.mkdir(parents=True, exist_ok=True)
        destination = RESUME_DIR / "Pratham_Jaiswal_Resume.pdf"

        # Archive previous versions before replacing the canonical latest file.
        archive_old_resumes(destination)

        destination.write_bytes(content)
        os.chmod(destination, 0o600)

        # Activating a file does not upload it to Naukri.
        set_env_value("INPUT_RESUME_PATH", str(destination))
        await interaction.followup.send(
            f"✅ **{destination.name}** is now the active resume.\n"
            "It has been saved on the VM, but not uploaded to Naukri. "
            "Use `/run` with Resume when you want to upload it.",
            ephemeral=True,
        )
    except Exception as exc:
        print(f"Resume upload error: {type(exc).__name__}: {exc}")
        await interaction.followup.send(
            "❌ Could not save the resume. Check the bot logs on the VM.",
            ephemeral=True,
        )


@bot.tree.command(name="resume_list", description="List saved resume PDFs")
async def resume_list_command(interaction: discord.Interaction):
    if not await require_owner(interaction):
        return

    files = resume_files()
    active = active_resume_path()
    if not files:
        message = "No resume PDFs have been saved yet."
    else:
        lines = []
        for path in files[:15]:
            marker = " **(active)**" if active and path.resolve() == active.resolve() else ""
            lines.append(f"• `{path.name}`{marker}")
        message = "\n".join(lines)

    await interaction.response.send_message(message, ephemeral=True)


@bot.tree.command(name="resume_active", description="Show the active resume")
async def resume_active_command(interaction: discord.Interaction):
    if not await require_owner(interaction):
        return

    path = active_resume_path()
    if not path or not path.is_file():
        message = "❌ The configured active resume file is missing."
    else:
        message = f"📄 Active resume: `{path.name}`"

    await interaction.response.send_message(message, ephemeral=True)


@bot.tree.command(name="resume_switch", description="Switch to a previously saved PDF")
@app_commands.describe(filename="Exact filename from /resume_list")
async def resume_switch_command(
    interaction: discord.Interaction,
    filename: str,
):
    if not await require_owner(interaction):
        return

    # Match only a basename in the dedicated resume directory.
    if Path(filename).name != filename:
        await interaction.response.send_message(
            "Provide only a filename, not a path.", ephemeral=True
        )
        return

    candidate = (RESUME_DIR / filename).resolve()
    if candidate.parent != RESUME_DIR.resolve() or not candidate.is_file():
        await interaction.response.send_message(
            "That saved resume was not found. Use `/resume_list`.",
            ephemeral=True,
        )
        return

    if candidate.suffix.lower() != ".pdf":
        await interaction.response.send_message(
            "Only PDF resumes can be activated.", ephemeral=True
        )
        return

    set_env_value("INPUT_RESUME_PATH", str(candidate))
    await interaction.response.send_message(
        f"✅ `{candidate.name}` is now active. "
        "Use `/run` with Resume to upload it to Naukri.",
        ephemeral=True,
    )


@bot.tree.command(name="schedule_show", description="Show today's saved schedule")
async def schedule_show_command(interaction: discord.Interaction):
    if not await require_owner(interaction):
        return

    state = read_state()
    if not state:
        message = "No readable schedule exists yet."
    else:
        lines = [
            f"**Schedule for {state.get('date', 'unknown date')}** "
            f"({local_timezone_name()})"
        ]
        for item in sorted(state.get("runs", []), key=lambda r: r["time"]):
            lines.append(
                f"• {item['time']} — {item['action']} — "
                f"{item['status']} (attempts: {item['attempts']})"
            )
        message = "\n".join(lines)

    await interaction.response.send_message(message, ephemeral=True)


@bot.tree.command(name="schedule_config", description="Set update count and schedule windows")
@app_commands.describe(
    updates_per_day="Number of active windows, at least 2",
    windows="JSON array of start, end, and action objects",
)
async def schedule_config_command(
    interaction: discord.Interaction,
    updates_per_day: int,
    windows: str,
):
    if not await require_owner(interaction):
        return

    try:
        parsed_windows = parse_windows_json(windows)
        cfg = update_config({
            "updates_per_day": updates_per_day,
            "windows": parsed_windows,
        })
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        await interaction.response.send_message(
            f"Configuration was not changed: {exc}", ephemeral=True
        )
        return

    await interaction.response.send_message(
        f"Saved {cfg['updates_per_day']} updates across {len(cfg['windows'])} windows. "
        f"Schedule times use the VM timezone ({local_timezone_name()}). "
        "The current saved schedule is unchanged; regenerate it when permitted "
        "or let the next schedule use these settings.",
        ephemeral=True,
    )


@bot.tree.command(name="schedule_regenerate", description="Regenerate today's schedule")
async def schedule_regenerate_command(interaction: discord.Interaction):
    if not await require_owner(interaction):
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    result = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, str(SCHEDULER_FILE), "generate", "--force"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode == 0:
        await interaction.followup.send(
            f"✅ Schedule regenerated.\n{result.stdout[-1500:]}",
            ephemeral=True,
        )
    else:
        detail = (result.stderr or result.stdout or "Unknown error")[-1200:]
        await interaction.followup.send(
            f"❌ Schedule not changed.\n{detail}", ephemeral=True
        )


@bot.tree.command(name="status", description="Show bot and scheduler status")
async def status_command(interaction: discord.Interaction):
    if not await require_owner(interaction):
        return

    state = read_state()
    cron = subprocess.run(
        ["systemctl", "is-active", "cron"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip() or "unknown"

    now = local_now()
    timezone = local_timezone_name(now)
    if state:
        done = sum(r["status"] == "done" for r in state.get("runs", []))
        failed = sum(r["status"] == "failed" for r in state.get("runs", []))
        pending = sum(r["status"] == "pending" for r in state.get("runs", []))
        schedule_line = (
            f"Schedule date: {state.get('date')}\n"
            f"Updates: {done} done, {pending} pending, {failed} failed"
        )
    else:
        schedule_line = "No readable saved schedule."

    message = (
        "🤖 **Naukri Bot status**\n"
        f"Bot: online\nCron service: {cron}\n"
        f"Local time ({timezone}): {now:%Y-%m-%d %H:%M:%S}\n"
        f"{schedule_line}"
    )
    await interaction.response.send_message(message, ephemeral=True)


@bot.event
async def on_error(event, *args, **kwargs):
    print(f"Unhandled Discord event error: {event}")
    notify(f"🚨 Naukri Discord bot error in event: {event}")


def main():
    cfg = load_env()
    token = cfg.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN is missing from .env")
    if not cfg.get("DISCORD_USER_ID") or not cfg.get("DISCORD_GUILD_ID"):
        raise RuntimeError("DISCORD_USER_ID or DISCORD_GUILD_ID is missing from .env")
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
