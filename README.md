# Naukri Profile Manager 📄

Automate your [Naukri.com](https://www.naukri.com/) profile updates with a
self-hosted scheduler, an optional Discord bot, and a reusable GitHub Action.

Update your resume headline, upload and manage resumes, schedule daily profile
updates, and receive notifications—all from your own Linux server. 🚀

![Codefactor](https://img.shields.io/codefactor/grade/github/pratham-jaiswal/naukri-profile-manager?style=flat&label=Code%20Quality&labelColor=%23201f31)
![GitHub License](https://img.shields.io/github/license/pratham-jaiswal/naukri-profile-manager?style=flat&label=License&labelColor=%23201f31)

## ✨ Features

- 🔄 **Automated scheduling:** Run updates at randomized times within
  configurable daily windows.
- 📝 **Resume headline updates:** Update your Naukri resume headline (maximum
  250 characters).
- 📤 **Resume uploads:** Upload a resume directly to Naukri.
- 📂 **Resume management:** Store, list, activate, and switch between PDF
  resumes.
- 🤖 **Optional Discord bot:** Manage updates and resumes using slash commands.
- 🔔 **Optional Discord notifications:** Receive schedule information, update
  results, and failure notifications.
- ⚡ **Manual execution:** Run a headline update, resume upload, or both on
  demand.
- 🐧 **Self-hosted deployment:** Run on a Linux server using cron and systemd.
- 🛠️ **GitHub Action:** Alternatively, use the updater through GitHub Actions
  with a self-hosted runner.

## 🚀 Before you begin: Naukri account details

You'll need three pieces of information from your Naukri account.

| Setting            | What to enter                                                                                                     |
| ------------------ | ----------------------------------------------------------------------------------------------------------------- |
| `INPUT_USERNAME`   | The **email address you use to log in to Naukri.com**. This is your Naukri login username, not your display name. |
| `INPUT_PASSWORD`   | Your Naukri account password.                                                                                     |
| `INPUT_PROFILE_ID` | The unique profile ID required by the updater to identify your Naukri profile.                                    |

### 🔍 How to find your Naukri Profile ID

Use the video guide below to locate your profile ID.

**Video guide:**

https://github.com/user-attachments/assets/44f2744e-672d-48b6-b8b7-1de1dfb7217c

Keep these values private. Never publish your Naukri password or include it in a
Git commit.

## 🧱 Choose how you want to use the project

You can use the core scheduler without Discord, or enable Discord integration
for notifications and remote control.

| Component                 | Required?                           | Purpose                                                   |
| ------------------------- | ----------------------------------- | --------------------------------------------------------- |
| Naukri updater            | Yes                                 | Updates your Naukri profile.                              |
| Python scheduler and cron | Yes for automated scheduled updates | Generates and executes the daily schedule.                |
| Discord webhook           | Optional                            | Sends notifications to a Discord channel.                 |
| Discord bot               | Optional                            | Lets you manage updates and resumes using slash commands. |
| GitHub Actions            | Optional alternative                | Runs the updater through a GitHub workflow.               |

**Recommended setup:** Run the scheduler on your Linux server. Add a Discord
webhook if you want notifications, and install the Discord bot if you also want
to manage your profile remotely.

## ⚠️ Important: Regional access

Naukri may restrict or behave differently for requests originating from certain
regions.

GitHub-hosted runners, which typically operate outside India, may not work
reliably. A self-hosted runner or Linux server in a region where Naukri is
accessible may be necessary.

This project has been tested on an Ubuntu server in Oracle Cloud's Mumbai
region.

## 🖥️ Self-hosted setup

### Prerequisites

- Ubuntu Linux server
- Node.js (use the version in `.node-version`)
- Yarn 1.22
- Python 3 and `venv`
- Git
- A Naukri.com account and the details listed above

Discord is not required for the core updater and scheduler. Complete the Discord
sections only if you want notifications or remote management.

### 1. Clone the repository

```bash
git clone https://github.com/pratham-jaiswal/naukri-profile-manager.git
cd naukri-profile-manager
```

### Quick start

For local development or a non-production machine, use the helper scripts:

```bash
yarn setup
yarn start
```

If you want to skip the interactive `.env` prompt and edit the file yourself later:

```bash
yarn setup -- --skip-env
```

To validate the config without starting anything:

```bash
yarn start:check
```

The start script validates the Naukri settings, generates the scheduler, and
only launches the Discord bot when all required bot variables are present. On
non-Linux hosts, the scheduler still generates a local schedule but skips cron
installation because `crontab` is not available there.

### Production bot management

On the Linux production VM, the bot is managed as a systemd service. If the
service is already running, restart it; otherwise start it.

```bash
sudo systemctl restart naukri-discord-bot.service
# or
sudo systemctl start naukri-discord-bot.service
sudo systemctl status naukri-discord-bot.service --no-pager
sudo journalctl -u naukri-discord-bot.service -n 60 --no-pager
```

Use the same pattern when deploying a new service or checking recent logs after a
restart.

### 2. Install updater dependencies

```bash
yarn install --frozen-lockfile
yarn package
```

This builds the distributable GitHub Action in `dist/`.

### 3. Configure your environment

Create `.env` from the placeholder template without overwriting an existing
file:

```bash
cp -n .env.example .env
nano .env
```

`.env.example` lists every supported variable with placeholders only. Replace
them locally; never put real credentials in the example file or commit the
populated `.env`.

Fill in the Naukri credentials and use an existing PDF path when performing
resume uploads.

The scheduler selects the appropriate update mode for each scheduled run. The
Discord variables can remain unconfigured if you don't use Discord.

Protect the environment file:

```bash
chmod 600 .env
```

**Never commit `.env` to Git.** It contains credentials and may contain Discord
tokens and webhook URLs.

### 4. Configure the scheduler

Edit `scheduler/config.json`:

```json
{
  "updates_per_day": 3,
  "windows": [
    {
      "start": "09:00",
      "end": "11:00",
      "action": "headline"
    },
    {
      "start": "13:00",
      "end": "15:00",
      "action": "resume"
    },
    {
      "start": "18:00",
      "end": "20:00",
      "action": "random"
    }
  ],
  "random_action_options": ["headline", "resume", "both"]
}
```

This example schedules three updates per day:

- Morning: update the headline.
- Afternoon: upload a resume.
- Evening: randomly choose a headline update, resume upload, or both.

Times are selected randomly within the configured windows. The end of a window
is exclusive: `09:00`–`11:00` permits times from 09:00 through 10:59.

The scheduler and cron use the VM's system timezone as their only timezone
source. Changing the VM timezone with `timedatectl` changes the effective
schedule timezone; there is no timezone setting in `scheduler/config.json` or
the Discord bot. Existing config files with a `timezone` property are accepted
but the property is ignored. Remove it manually, or save schedule settings with
`/schedule_config` to write a clean config.

### 5. Enable cron scheduling

The scheduler generates daily cron entries and runs updates using the VM's
system-local time. Cron interprets the generated times in that same host
timezone. No `CRON_TZ` assignments are written.

On each installation, the scheduler replaces only the block from
`# BEGIN NAUKRI GENERATED JOBS` through `# END NAUKRI GENERATED JOBS`. Lines
outside it, including the permanent `00:05` schedule-generator job, are
preserved in their original relative order, except for a legacy `CRON_TZ`
restoration assignment immediately after the old block, which is removed. Do not
put custom jobs inside the marked block. The generated block contains only the
selected update jobs, with no timezone environment assignments.

To inspect the VM timezone, run `timedatectl`. Changing it with
`sudo timedatectl set-timezone Region/City` affects future scheduling and cron
execution. The production VM currently uses `Asia/Kolkata`.

Example commands:

```bash
python3 scheduler/scheduler.py generate --dry-run
python3 scheduler/scheduler.py generate
python3 scheduler/scheduler.py run 1
```

The dry run prints the proposed schedule and managed cron block without changing
saved state or the crontab. After normal `generate`, inspect the installed
crontab as the same user that runs the scheduler:

```bash
crontab -l
```

Check that unrelated entries and the permanent generator remain intact, that the
generated block has no `CRON_TZ` assignment, and that no extra generation job
was added. The `run 1` command performs a real update, so use it only when you
intend to modify your Naukri profile.

Keep the server running for scheduled jobs to execute.

If you are running the project on a non-Linux system, the scheduler can still
validate config and generate a schedule locally, but automatic recurring cron
jobs will not be installed unless the host has `cron`/`crontab` available.
Use a Linux VM or server for unattended scheduled automation.

## 🔔 Optional: Set up Discord notifications

A Discord webhook lets the scheduler send messages to a channel without
requiring the Discord bot.

### 1. Create a private Discord server

For personal use, create a private server containing **only you and your Naukri
Bot**.

Keep the notification channel private as well. This reduces the chance of
accidentally exposing profile information or allowing other people to see
operational notifications.

### 2. Create a notification channel

Create a text channel, for example:

`#naukri-notifications`

Restrict access to yourself and, if you use the bot in this server, the bot.

### 3. Create a webhook

1. Open your Discord server settings.
2. Go to **Integrations → Webhooks**.
3. Select **New Webhook**.
4. Give it a name, such as `Naukri Bot`.
5. Select `#naukri-notifications` as the destination channel.
6. Copy the webhook URL.

The exact menu labels may vary slightly depending on the Discord client.

### 4. Configure the webhook

Add the copied URL to `.env`:

```dotenv
DISCORD_WEBHOOK_URL=your_webhook_url
```

Treat the webhook URL like a password: anyone who obtains it may be able to post
messages to its channel.

The webhook is now configured for scheduler notifications. You do not need to
create a Discord bot application just to receive notifications.

## 🤖 Optional: Set up the Discord bot

The Discord bot provides remote controls for the updater and resume manager.

### 1. Create a Discord application

1. Open the
   [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **New Application**.
3. Name it `Naukri Bot`.
4. Open the application's **Bot** section and add a bot if prompted.
5. Generate or reset its bot token and copy it securely.

**Never publish the bot token or commit it to Git.** If a token is exposed,
reset it immediately.

### 2. Invite the bot to your private server

In the Developer Portal, open **OAuth2 → URL Generator**.

Select these scopes:

- `bot`
- `applications.commands`

Grant only the permissions the bot needs, such as viewing its private channel
and sending messages. Use the generated URL to invite the bot to your private
server.

Do not make the server or notification channel public.

### 3. Find your Discord IDs

The bot uses your Discord user ID and the server's guild ID to restrict command
access.

To copy these IDs:

1. Open Discord's **User Settings → Advanced**.
2. Enable **Developer Mode**.
3. Right-click or open the context menu for your user and select **Copy User
   ID**.
4. Open your server's context menu and select **Copy Server ID**.

The labels may vary slightly between desktop and mobile.

### 4. Configure the bot

Add the values to `.env`:

```dotenv
DISCORD_BOT_TOKEN=your_bot_token
DISCORD_USER_ID=your_discord_user_id
DISCORD_GUILD_ID=your_discord_server_id
```

The bot is configured to restrict commands to the specified user and server.
Keep the server private as an additional layer of protection.

### 5. Install and run the bot

Create a dedicated Python virtual environment for the bot and install the pinned bot requirements:

```bash
sudo apt install -y python3-venv

python3 -m venv bot/venv
source bot/venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r bot/requirements.txt
```

On Windows PowerShell, use:

```powershell
py -m venv bot\venv
.\bot\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r bot\requirements.txt
```

Start the bot for initial testing:

```bash
python bot/bot.py
```

If you are using the venv in a shell that is already activated, the command above works without prefixing `python`; otherwise use the venv path directly, for example:

```bash
bot/venv/bin/python bot/bot.py
```

Once it connects, test `/status` in your private server.

### 6. Keep the bot running

To keep the bot active after closing SSH, configure it as a systemd service. The
existing production VM still uses the legacy directory
`/home/ubuntu/naukri-resume-action`; keep that path when managing its current
service or cron jobs.

For a new installation, replace the paths below with the actual clone path.

```bash
sudo tee /etc/systemd/system/naukri-discord-bot.service >/dev/null <<'EOF'
[Unit]
Description=Naukri Bot Discord Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/naukri-resume-action
ExecStart=/home/ubuntu/naukri-resume-action/bot/venv/bin/python /home/ubuntu/naukri-resume-action/bot/bot.py
Restart=always
RestartSec=10
UMask=0077

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now naukri-discord-bot
sudo systemctl status naukri-discord-bot --no-pager
```

Change the paths and username if your installation directory differs. This
service keeps the bot running while the VM is running; it does not start the VM
itself.

## 🎮 Discord bot commands

| Command                | Description                                                                                   |
| ---------------------- | --------------------------------------------------------------------------------------------- |
| `/run`                 | Run a headline update, resume upload, or both.                                                |
| `/headline`            | Save a new headline for future updates.                                                       |
| `/resume_upload`       | Upload a PDF to the server and make it active. It does not automatically upload it to Naukri. |
| `/resume_list`         | List stored resumes.                                                                          |
| `/resume_active`       | Show the active resume.                                                                       |
| `/resume_switch`       | Switch to an existing resume.                                                                 |
| `/schedule_show`       | Display the generated schedule.                                                               |
| `/schedule_config`     | Set the update count and schedule windows using JSON.                                         |
| `/schedule_regenerate` | Regenerate the schedule when permitted.                                                       |
| `/status`              | Check bot and updater status.                                                                 |

`/schedule_config` accepts a JSON array such as
`[ {"start":"09:00","end":"11:00","action":"headline"}, {"start":"13:00","end":"15:00","action":"resume"}, {"start":"18:00","end":"20:00","action":"random"} ]`.
The update count must be at least 2 and no greater than the number of
non-overlapping windows; the first two actions must remain `headline` and
`resume`. Invalid settings are rejected without changing the config. Saved
settings apply when a schedule is next generated; they do not overwrite today's
saved schedule.

### Resume handling

The bot stores uploaded resumes on the server. A new upload becomes the active
resume under the canonical filename `Pratham_Jaiswal_Resume.pdf`; older resumes
are archived with timestamped filenames.

PDF uploads are limited to 10 MiB. Uploading or switching a resume changes the
active file but does not itself upload it to Naukri. Use `/run` with the resume
action when you want to upload it.

## 🛠️ Alternative: GitHub Actions

You can use the updater through GitHub Actions instead of the Python scheduler.

Create `.github/workflows/update-profile.yml`:

```yaml
name: Update Naukri Profile

on:
  schedule:
    - cron: '0 0 * * *'
  workflow_dispatch:

jobs:
  update-profile:
    runs-on: self-hosted

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Update Naukri profile
        uses: ./
        with:
          mode: both
          username: ${{ secrets.NAUKRI_USERNAME }}
          password: ${{ secrets.NAUKRI_PASSWORD }}
          profile_id: ${{ secrets.NAUKRI_PROFILE_ID }}
          resume_headline: ${{ secrets.NAUKRI_RESUME_HEADLINE }}
          resume_path: /home/runner/private/Resume.pdf
```

The PDF must already be available at the specified path on the self-hosted
runner. Keep private resumes out of the repository. GitHub Actions cron uses
UTC.

### Action inputs

| Input             | Description                                    | Required                                            |
| ----------------- | ---------------------------------------------- | --------------------------------------------------- |
| `username`        | Naukri login email                             | Yes                                                 |
| `password`        | Naukri password                                | Yes                                                 |
| `profile_id`      | Naukri profile ID                              | Yes                                                 |
| `resume_path`     | Path or newline-separated list of resume paths | Required for `resume` and `both` modes              |
| `mode`            | `headline`, `resume`, or `both`                | No; defaults to `both`                              |
| `resume_headline` | Resume headline, up to 250 characters          | Required at runtime for `headline` and `both` modes |

The current updater focuses on resume headline updates and resume uploads. The
original profile-summary update behavior is not implemented in the current
`src/main.ts`.

### GitHub Secrets

In your repository, go to **Settings → Secrets and variables → Actions** and
add:

- `NAUKRI_USERNAME`
- `NAUKRI_PASSWORD`
- `NAUKRI_PROFILE_ID`
- `NAUKRI_RESUME_HEADLINE` (for the example workflow)

Never hardcode credentials in workflow files.

## 🧪 Local testing and troubleshooting

Run the safe local checks from the repository root. These tests do not contact
Naukri or modify a profile.

```bash
yarn test
yarn lint
yarn format:check
yarn package
python -m unittest scheduler.test_scheduler_config
```

Run these commands in the same order as the CI workflow. The test script passes
its Node flags directly, so `yarn test` works in Windows shells as well as Linux
CI.

### Check scheduler logs

```bash
tail -n 100 scheduler/cron.log
```

### Check bot status

```bash
sudo systemctl status naukri-discord-bot --no-pager
```

### Inspect bot logs

```bash
sudo journalctl -u naukri-discord-bot -n 100 --no-pager
```

### Common issues

- **Authentication failures:** Verify the Naukri login email, password, and
  profile ID.
- **Resume upload failures:** Check that the selected file exists, is a valid
  PDF, and is accessible to the Ubuntu user.
- **Missing Discord notifications:** Verify `DISCORD_WEBHOOK_URL`, the
  destination channel, and channel notification settings.
- **Bot not responding:** Check the bot token, user ID, guild ID,
  application-command permissions, and systemd service.
- **Scheduled update did not run:** Verify that the VM is running, cron is
  active, the VM system timezone matches your intended schedule, and the
  generated schedule is current.

## 🔒 Security

- Never commit `.env`, credentials, bot tokens, webhook URLs, or personal resume
  files.
- Use GitHub Secrets for GitHub Actions credentials.
- Keep your Discord server and notification channel private.
- Restrict bot commands to your own Discord user ID and server.
- Keep your server and dependencies updated.
- Review logs before sharing them, as they may contain personal information or
  local file paths.

## 🤝 Contributing

Contributions are welcome!

1. Fork the repository.
2. Create a feature branch: `git checkout -b feature/amazing-feature`.
3. Set up the development environment.
4. Make and test your changes.
5. Commit your changes and push the branch.
6. Open a pull request.

Do not commit secrets, personal resume files, generated runtime state, or local
environment files.

## ⭐ Support

If you find this project useful, consider starring the repository. Bug reports,
suggestions, and contributions are welcome.

## 📄 License

This project is licensed under the MIT License. See the `LICENSE` file for
details.
