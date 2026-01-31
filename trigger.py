import json
import os
import subprocess

from dotenv import load_dotenv

from CEACStatusBot import (
    EmailNotificationHandle,
    NotificationManager,
    TelegramNotificationHandle,
)

# --- Load .env if present, else fallback to system env ---
if os.path.exists(".env"):
    load_dotenv(dotenv_path=".env")  # loads into os.environ
else:
    print(".env not found, using system environment only")


def _ensure_status_file():
    if not os.path.exists("status_record.json"):
        with open("status_record.json", "w") as file:
            json.dump({"statuses": []}, file)


def _get_github_token():
    return os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")


def download_artifact():
    repo = os.getenv("GITHUB_REPOSITORY")
    if not repo:
        print("GITHUB_REPOSITORY not set; skipping artifact download.")
        _ensure_status_file()
        return

    token = _get_github_token()
    if not token:
        print("No GitHub token available; skipping artifact download.")
        _ensure_status_file()
        return

    env = os.environ.copy()
    env["GH_TOKEN"] = token

    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{repo}/actions/artifacts"],
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
        artifacts = json.loads(result.stdout or "{}")
        artifact_exists = any(artifact["name"] == "status-artifact" for artifact in artifacts.get("artifacts", []))

        if artifact_exists:
            subprocess.run(["gh", "run", "download", "--name", "status-artifact"], check=True, env=env)
        else:
            _ensure_status_file()
    except Exception as e:
        print(f"Error downloading artifact: {e}")
        _ensure_status_file()


if not os.path.exists("status_record.json"):
    download_artifact()

try:
    LOCATION = os.environ["LOCATION"]
    NUMBER = os.environ["NUMBER"]
    PASSPORT_NUMBER = os.environ["PASSPORT_NUMBER"]
    SURNAME = os.environ["SURNAME"]
    notificationManager = NotificationManager(LOCATION, NUMBER, PASSPORT_NUMBER, SURNAME)
except KeyError as e:
    raise RuntimeError(f"Missing required env var: {e}") from e


# --- Optional: Email notifications ---
FROM = os.getenv("FROM")
TO = os.getenv("TO")
PASSWORD = os.getenv("PASSWORD")
SMTP = os.getenv("SMTP", "")

if FROM and TO and PASSWORD:
    emailNotificationHandle = EmailNotificationHandle(FROM, TO, PASSWORD, SMTP)
    notificationManager.addHandle(emailNotificationHandle)
else:
    print("Email notification config missing or incomplete")


# --- Optional: Telegram notifications ---
BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
CHAT_ID = os.getenv("TG_CHAT_ID")

if BOT_TOKEN and CHAT_ID:
    tgNotif = TelegramNotificationHandle(BOT_TOKEN, CHAT_ID)
    notificationManager.addHandle(tgNotif)
else:
    print("Telegram bot notification config missing or incomplete")


# --- Send notifications ---
notificationManager.send(force_notify=True)
