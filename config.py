from dotenv import load_dotenv
import os

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMINS = list(map(int, os.getenv("ADMINS", "").split(",")))
CHANNEL_PUBLIC = os.getenv("CHANNEL_PUBLIC")
CHANNEL_PRIVATE = os.getenv("CHANNEL_PRIVATE")
DB_PATH = os.getenv("DB_PATH", "data/kinobot.db")
