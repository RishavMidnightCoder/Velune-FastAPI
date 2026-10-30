import io
import json
import logging
from datetime import timedelta
import base64

import httpx
import os
import subprocess
import tempfile

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from groq import AsyncGroq
from PIL import Image
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session


from src.users.model import User
from src.utils.constant import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    CLOUDFLARE_ACCOUNT_ID,
    CLOUDFLARE_API_TOKEN,
    CLOUDFLARE_IMAGE_MODEL,
    CLOUDFLARE_REF_IMAGE_MODEL,
    GROQ_API_KEY,
    IMAGE_API_KEY,
    IMAGE_API_URL,
    IMAGE_MODEL,
    IMAGE_PROVIDER,
    IMAGE_STEPS,
    ROLE_ADMIN,
    SECRET_KEY,
)
from src.utils.db import get_db, utcnow

logger = logging.getLogger("velune.image")


# ---------- DTO base: snake_case in Python, camelCase in JSON ----------
class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


# ---------- Passwords ----------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


# ---------- JWT ----------
def create_access_token(user_id: int, role: str) -> str:
    now = utcnow()
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


# ---------- Auth dependencies ----------
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if creds is None:
        raise unauthorized
    try:
        payload = decode_access_token(creds.credentials)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise unauthorized
    user = db.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    # The role is re-read from the database, not trusted from the token.
    if user.role != ROLE_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


# ---------- Groq client ----------
_groq_client: AsyncGroq | None = None


def get_groq_client() -> AsyncGroq:
    global _groq_client
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY is not configured")
    if _groq_client is None:
        _groq_client = AsyncGroq(api_key=GROQ_API_KEY)
    return _groq_client


# ---------- Server-Sent Events ----------
def sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

# ---------- Image generation (Cloudflare Workers AI or Together AI) ----------
async def _cloudflare_image(prompt: str) -> bytes:
    if not CLOUDFLARE_ACCOUNT_ID or not CLOUDFLARE_API_TOKEN:
        raise RuntimeError("CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN are not configured")

    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}"
        f"/ai/run/{CLOUDFLARE_IMAGE_MODEL}"
    )
    async with httpx.AsyncClient(timeout=90) as client:
        res = await client.post(
            url,
            headers={"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"},
            json={"prompt": prompt[:2000], "steps": IMAGE_STEPS},
        )
    if res.status_code != 200:
        raise RuntimeError(f"Cloudflare image error {res.status_code}: {res.text[:300]}")

    body = res.json()
    result = body.get("result", body)  # the REST API wraps the output in "result"
    image_b64 = result.get("image") if isinstance(result, dict) else None
    if not image_b64:
        raise RuntimeError("Cloudflare returned no image")
    return base64.b64decode(image_b64)


def shrink_reference(data: bytes) -> bytes:
    """Reference images for FLUX.2 must be smaller than 512x512."""
    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((500, 500))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


async def _cloudflare_image_with_refs(prompt: str, refs: list[bytes]) -> bytes:
    if not CLOUDFLARE_ACCOUNT_ID or not CLOUDFLARE_API_TOKEN:
        raise RuntimeError("CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN are not configured")

    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}"
        f"/ai/run/{CLOUDFLARE_REF_IMAGE_MODEL}"
    )
    files = {
        f"input_image_{i}": (f"ref{i}.png", shrink_reference(img), "image/png")
        for i, img in enumerate(refs[:4])
    }
    async with httpx.AsyncClient(timeout=120) as client:
        res = await client.post(
            url,
            headers={"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"},
            data={"prompt": prompt[:2000], "width": "1024", "height": "576"},
            files=files,
        )
    if res.status_code != 200:
        raise RuntimeError(f"Cloudflare ref-image error {res.status_code}: {res.text[:300]}")

    body = res.json()
    result = body.get("result", body)
    image_b64 = result.get("image") if isinstance(result, dict) else None
    if not image_b64:
        raise RuntimeError("Cloudflare returned no image")
    return base64.b64decode(image_b64)


async def _together_image(prompt: str) -> bytes:
    if not IMAGE_API_KEY:
        raise RuntimeError("IMAGE_API_KEY is not configured")

    payload = {
        "model": IMAGE_MODEL,
        "prompt": prompt,
        "width": 1024,
        "height": 576,
        "steps": IMAGE_STEPS,
        "n": 1,
        "response_format": "b64_json",
    }
    async with httpx.AsyncClient(timeout=90) as client:
        res = await client.post(
            IMAGE_API_URL, json=payload, headers={"Authorization": f"Bearer {IMAGE_API_KEY}"}
        )
        if res.status_code != 200:
            raise RuntimeError(f"Together image error {res.status_code}: {res.text[:300]}")
        item = res.json()["data"][0]
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"])
        if item.get("url"):
            img = await client.get(item["url"])
            img.raise_for_status()
            return img.content
    raise RuntimeError("Image provider returned no image")


def image_to_video_bytes(image_bytes: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        src, out = os.path.join(tmp, "in.png"), os.path.join(tmp, "out.mp4")
        with open(src, "wb") as f:
            f.write(image_bytes)
        vf = (
            "scale=2048:-2,zoompan=z='min(zoom+0.0015,1.25)':"
            "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=75:s=1024x576:fps=25,format=yuv420p"
        )
        subprocess.run(
            ["ffmpeg", "-y", "-i", src, "-vf", vf, "-c:v", "libx264", "-movflags", "+faststart", out],
            check=True, capture_output=True, timeout=60,
        )
        with open(out, "rb") as f:
            return f.read()


async def generate_image_bytes(prompt: str, refs: list[bytes] | None = None) -> bytes:
    if IMAGE_PROVIDER == "together":
        return await _together_image(prompt)
    if refs:
        try:
            return await _cloudflare_image_with_refs(prompt, refs)
        except Exception:
            logger.exception("Reference image call failed, falling back to text-only image")
    return await _cloudflare_image(prompt)