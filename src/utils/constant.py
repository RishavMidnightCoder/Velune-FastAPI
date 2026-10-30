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
MAX_UPLOAD_BYTES = 4 * 1024 * 1024

IMAGE_ENABLED = os.getenv("IMAGE_ENABLED", "true").lower() == "true"
IMAGE_API_URL = os.getenv("IMAGE_API_URL", "https://api.together.ai/v1/images/generations")
IMAGE_API_KEY = os.getenv("IMAGE_API_KEY", "")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell")
IMAGE_STEPS = int(os.getenv("IMAGE_STEPS", "4"))
IMAGE_EVERY_N = max(1, int(os.getenv("IMAGE_EVERY_N", "3")))
IMAGE_STYLE_SUFFIX = (
    "cinematic film still, dramatic lighting, rich detail, wide 16:9 composition, "
    "safe for work, no text, no captions, no watermark"
)
# Used only for stories whose age rating is adult (18+ / Adult / Mature).
IMAGE_STYLE_SUFFIX_ADULT = (
    "cinematic film still, dramatic moody lighting, rich detail, wide 16:9 composition, "
    "mature dark tone, no text, no captions, no watermark"
)

IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "cloudflare").lower()
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")
CLOUDFLARE_IMAGE_MODEL = os.getenv("CLOUDFLARE_IMAGE_MODEL", "@cf/black-forest-labs/flux-1-schnell")
# Reference-image model: keeps the faces/look of the story thumbnail.
CLOUDFLARE_REF_IMAGE_MODEL = os.getenv(
    "CLOUDFLARE_REF_IMAGE_MODEL", "@cf/black-forest-labs/flux-2-klein-9b"
)