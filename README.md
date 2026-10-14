# Naukri Profile Manager 📄

Automate your [Naukri.com](https://www.naukri.com/) profile updates with a self-hosted scheduler, an optional Discord bot, and a reusable GitHub Action.

Update your resume headline, upload and manage resumes, schedule daily profile updates, and receive notifications—all from your own Linux server. 🚀

## ✨ Features

- 🔄 **Automated scheduling:** Run updates at randomized times within configurable daily windows.
- 📝 **Resume headline updates:** Update your Naukri resume headline (maximum 250 characters).
- 📤 **Resume uploads:** Upload a resume directly to Naukri.
- 📂 **Resume management:** Store, list, activate, and switch between PDF resumes.
- 🤖 **Optional Discord bot:** Manage updates and resumes using slash commands.
- 🔔 **Optional Discord notifications:** Receive schedule information, update results, and failure notifications.
- ⚡ **Manual execution:** Run a headline update, resume upload, or both on demand.
- 🐧 **Self-hosted deployment:** Run on a Linux server using cron and systemd.
- 🛠️ **GitHub Action:** Alternatively, use the updater through GitHub Actions with a self-hosted runner.

## 🚀 Before you begin: Naukri account details

You'll need three pieces of information from your Naukri account.

| Setting | What to enter |
|---|---|
| `INPUT_USERNAME` | The **email address you use to log in to Naukri.com**. This is your Naukri login username, not your display name. |
| `INPUT_PASSWORD` | Your Naukri account password. |
| `INPUT_PROFILE_ID` | The unique profile ID required by the updater to identify your Naukri profile. |

### 🔍 How to find your Naukri Profile ID

Use the video guide below to locate your profile ID.

**Video guide:**

https://github.com/user-attachments/assets/44f2744e-672d-48b6-b8b7-1de1dfb7217c

Keep these values private. Never publish your Naukri password or include it in a Git commit.

## 🧱 Choose how you want to use the project

You can use the core scheduler without Discord, or enable Discord integration for notifications and remote control.

| Component | Required? | Purpose |
|---|---|---|
| Naukri updater | Yes | Updates your Naukri profile. |
| Python scheduler and cron | Yes for automated scheduled updates | Generates and executes the daily schedule. |
| Discord webhook | Optional | Sends notifications to a Discord channel. |
| Discord bot | Optional | Lets you manage updates and resumes using slash commands. |
| GitHub Actions | Optional alternative | Runs the updater through a GitHub workflow. |

**Recommended setup:** Run the scheduler on your Linux server. Add a Discord webhook if you want notifications, and install the Discord bot if you also want to manage your profile remotely.

## ⚠️ Important: Regional access

Naukri may restrict or behave differently for requests originating from certain regions.

GitHub-hosted runners, which typically operate outside India, may not work reliably. A self-hosted runner or Linux server in a region where Naukri is accessible may be necessary.

This project has been tested on an Ubuntu server in Oracle Cloud's Mumbai region.

## 🖥️ Self-hosted setup

### Prerequisites

- Ubuntu Linux server
- Node.js and npm
- Python 3 and `venv`
- Git
- A Naukri.com account and the details listed above

Discord is not required for the core updater and scheduler. Complete the Discord sections only if you want notifications or remote management.

### 1. Clone the repository

```bash
git clone https://github.com/pratham-jaiswal/naukri-profile-manager.git
cd naukri-profile-manager
```

### 2. Install updater dependencies

```bash
npm install
npm run package
```

This builds the distributable GitHub Action in `dist/`.

### 3. Configure your environment

Create a `.env` file in the repository root:

```bash
nano .env
```

Add your configuration:

```dotenv
# Naukri credentials
INPUT_USERNAME=
INPUT_PASSWORD=
INPUT_PROFILE_ID=

# Updater configuration
INPUT_MODE=both
INPUT_RESUME_HEADLINE=
INPUT_RESUME_PATH=/home/ubuntu/naukri-data/resumes/Pratham_Jaiswal_Resume.pdf

# Optional: Discord webhook notifications
DISCORD_WEBHOOK_URL=

# Optional: Discord bot
DISCORD_BOT_TOKEN=
DISCORD_USER_ID=
DISCORD_GUILD_ID=
```

Fill in the Naukri credentials and use an existing PDF path when performing resume uploads.

The scheduler selects the appropriate update mode for each scheduled run. The Discord variables can remain unconfigured if you don't use Discord.

Protect the environment file:

```bash
chmod 600 .env
```

**Never commit `.env` to Git.** It contains credentials and may contain Discord tokens and webhook URLs.

### 4. Configure the scheduler

Edit `scheduler/config.json`:

```json
{
  "timezone": "Asia/Kolkata",
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
  "random_action_options": [
    "headline",
    "resume",
    "both"
  ]
}
```

This example schedules three updates per day:

- Morning: update the headline.
- Afternoon: upload a resume.
- Evening: randomly choose a headline update, resume upload, or both.

Times are selected randomly within the configured windows. The end of a window is exclusive: `09:00`–`11:00` permits times from 09:00 through 10:59.

Adjust the windows and timezone to suit your needs. Ensure that the server timezone matches the scheduler configuration.

### 5. Enable cron scheduling

The scheduler generates daily cron entries and runs the updates at their selected times.

Example commands:

```bash
python3 scheduler/scheduler.py generate
python3 scheduler/scheduler.py run 1
```

The first command generates the schedule. The second runs update number 1 and is useful for testing; it performs a real update, so use it deliberately.

Keep the server running for scheduled jobs to execute.

## 🔔 Optional: Set up Discord notifications

A Discord webhook lets the scheduler send messages to a channel without requiring the Discord bot.

### 1. Create a private Discord server

For personal use, create a private server containing **only you and your Naukri Bot**.

Keep the notification channel private as well. This reduces the chance of accidentally exposing profile information or allowing other people to see operational notifications.

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

Treat the webhook URL like a password: anyone who obtains it may be able to post messages to its channel.

The webhook is now configured for scheduler notifications. You do not need to create a Discord bot application just to receive notifications.

## 🤖 Optional: Set up the Discord bot

The Discord bot provides remote controls for the updater and resume manager.

### 1. Create a Discord application

1. Open the [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **New Application**.
3. Name it `Naukri Bot`.
4. Open the application's **Bot** section and add a bot if prompted.
5. Generate or reset its bot token and copy it securely.

**Never publish the bot token or commit it to Git.** If a token is exposed, reset it immediately.

### 2. Invite the bot to your private server

In the Developer Portal, open **OAuth2 → URL Generator**.

Select these scopes:

- `bot`
- `applications.commands`

Grant only the permissions the bot needs, such as viewing its private channel and sending messages. Use the generated URL to invite the bot to your private server.

Do not make the server or notification channel public.

### 3. Find your Discord IDs

The bot uses your Discord user ID and the server's guild ID to restrict command access.

To copy these IDs:

1. Open Discord's **User Settings → Advanced**.
2. Enable **Developer Mode**.
3. Right-click or open the context menu for your user and select **Copy User ID**.
4. Open your server's context menu and select **Copy Server ID**.

The labels may vary slightly between desktop and mobile.

### 4. Configure the bot

Add the values to `.env`:

```dotenv
DISCORD_BOT_TOKEN=your_bot_token
DISCORD_USER_ID=your_discord_user_id
DISCORD_GUILD_ID=your_discord_server_id
```

The bot is configured to restrict commands to the specified user and server. Keep the server private as an additional layer of protection.

### 5. Install and run the bot

```bash
sudo apt install -y python3-venv

python3 -m venv bot/venv
bot/venv/bin/python -m pip install --upgrade pip
bot/venv/bin/python -m pip install "discord.py>=2.4,<3"
```

Start the bot for initial testing:

```bash
bot/venv/bin/python bot/bot.py
```

Once it connects, test `/status` in your private server.

### 6. Keep the bot running

To keep the bot active after closing SSH, configure it as a systemd service. For the default installation path and `ubuntu` user:

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

Change the paths and username if your installation directory differs. This service keeps the bot running while the VM is running; it does not start the VM itself.

## 🎮 Discord bot commands

| Command | Description |
|---|---|
| `/run` | Run a headline update, resume upload, or both. |
| `/headline` | Save a new headline for future updates. |
| `/resume_upload` | Upload a PDF to the server and make it active. It does not automatically upload it to Naukri. |
| `/resume_list` | List stored resumes. |
| `/resume_active` | Show the active resume. |
| `/resume_switch` | Switch to an existing resume. |
| `/schedule_show` | Display the generated schedule. |
| `/schedule_regenerate` | Regenerate the schedule when permitted. |
| `/status` | Check bot and updater status. |

### Resume handling

The bot stores uploaded resumes on the server. A new upload becomes the active resume under the canonical filename `Pratham_Jaiswal_Resume.pdf`; older resumes are archived with timestamped filenames.

PDF uploads are limited to 10 MiB. Uploading or switching a resume changes the active file but does not itself upload it to Naukri. Use `/run` with the resume action when you want to upload it.

## 🛠️ Alternative: GitHub Actions

You can use the updater through GitHub Actions instead of the Python scheduler.

Create `.github/workflows/update-profile.yml`:

```yaml
name: Update Naukri Profile

on:
  schedule:
    - cron: "0 0 * * *"
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
          resume_path: ./resumes/resume.pdf
```

The example assumes the PDF is available at `./resumes/resume.pdf` on the runner. GitHub Actions cron uses UTC.

See the original project's [Example Workflow Repository](https://github.com/jethalalCoder/Workflow/blob/main/.github/workflows/upload-resumeMain.yaml).

### Action inputs

| Input | Description | Required |
|---|---|---|
| `username` | Naukri login email | Yes |
| `password` | Naukri password | Yes |
| `profile_id` | Naukri profile ID | Yes |
| `resume_path` | Path or newline-separated list of resume paths | Yes in the current action metadata |
| `mode` | `headline`, `resume`, or `both` | No; defaults to `both` |
| `resume_headline` | Resume headline, up to 250 characters | Required at runtime for `headline` and `both` modes |

The current updater focuses on resume headline updates and resume uploads. The original profile-summary update behavior is not implemented in the current `src/main.ts`.

### GitHub Secrets

In your repository, go to **Settings → Secrets and variables → Actions** and add:

- `NAUKRI_USERNAME`
- `NAUKRI_PASSWORD`
- `NAUKRI_PROFILE_ID`
- `NAUKRI_RESUME_HEADLINE` (for the example workflow)

Never hardcode credentials in workflow files.

## 🧪 Local testing and troubleshooting

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

- **Authentication failures:** Verify the Naukri login email, password, and profile ID.
- **Resume upload failures:** Check that the selected file exists, is a valid PDF, and is accessible to the Ubuntu user.
- **Missing Discord notifications:** Verify `DISCORD_WEBHOOK_URL`, the destination channel, and channel notification settings.
- **Bot not responding:** Check the bot token, user ID, guild ID, application-command permissions, and systemd service.
- **Scheduled update did not run:** Verify that the VM is running, cron is active, the timezone is correct, and the generated schedule is current.

## 🔒 Security

- Never commit `.env`, credentials, bot tokens, webhook URLs, or personal resume files.
- Use GitHub Secrets for GitHub Actions credentials.
- Keep your Discord server and notification channel private.
- Restrict bot commands to your own Discord user ID and server.
- Keep your server and dependencies updated.
- Review logs before sharing them, as they may contain personal information or local file paths.

## 🤝 Contributing

Contributions are welcome!

1. Fork the repository.
2. Create a feature branch: `git checkout -b feature/amazing-feature`.
3. Set up the development environment.
4. Make and test your changes.
5. Commit your changes and push the branch.
6. Open a pull request.

Do not commit secrets, personal resume files, generated runtime state, or local environment files.

## ⭐ Support

If you find this project useful, consider starring the repository. Bug reports, suggestions, and contributions are welcome.

## 📄 License

This project is licensed under the MIT License. See the `LICENSE` file for details.
