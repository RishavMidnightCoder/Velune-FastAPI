import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/velune"
)
SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))

FRONTEND_ORIGINS = [
    o.strip() for o in os.getenv("FRONTEND_ORIGINS", "http://localhost:3000").split(",") if o.strip()
]

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

ADMIN_NAME = os.getenv("ADMIN_NAME", "Admin")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

ROLE_USER = "user"
ROLE_ADMIN = "admin"

STATUS_DRAFT = "draft"
STATUS_PUBLISHED = "published"

CHAT_HISTORY_LIMIT = 12

DEFAULT_CHOICES = ["Continue forward", "Look around carefully", "Ask what happens next"]

LANGUAGE_RULES = {
    "English": "Write in English.",
    "हिन्दी": "Write in Hindi using Devanagari script.",
    "Hinglish": "Write in Hinglish: Hindi written in Roman letters, mixed naturally with English.",
    "Auto Detect": "Reply in the same language the player uses in their latest message.",
}

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
MAX_UPLOAD_BYTES = 5 * 1024 * 1024