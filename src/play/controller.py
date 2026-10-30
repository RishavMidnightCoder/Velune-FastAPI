import asyncio
import json
import logging

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from src.characters.model import Character
from src.play.dtos import ActionDto, PlayStateOut, ProgressCardOut
from src.play.model import ChatMessage, UserProgress
from src.stories.model import Story
from src.uploads.controller import load_image_bytes, save_image_bytes, save_video_bytes
from src.users.model import User
from src.utils.constant import (
    CHAT_HISTORY_LIMIT,
    DEFAULT_CHOICES,
    GROQ_MODEL,
    IMAGE_ENABLED,
    IMAGE_EVERY_N,
    IMAGE_STYLE_SUFFIX,
    IMAGE_STYLE_SUFFIX_ADULT,
    LANGUAGE_RULES,
    STATUS_PUBLISHED,
)
from src.utils.db import SessionLocal
from src.utils.helper import (
    generate_image_bytes,
    get_groq_client,
    image_to_video_bytes,
    sse,
)

logger = logging.getLogger("velune.play")

# Replies cycle: image, image, 3-second video, repeat.
MEDIA_CYCLE = ["image", "image", "video"]

# A character whose role contains one of these words is the one the player controls.
PLAYER_ROLE_HINTS = ("protagonist", "player", "hero", "main")

REF_PROMPT_PREFIX = (
    "Image 0 is the cover art of this story. Keep the same characters, faces, hairstyles, outfits "
    "and cinematic look as image 0. New scene:"
)

RATING_RULES = {
    "all": "Content must suit all ages: no graphic violence, no strong language, nothing romantic beyond innocent.",
    "teen": "Content must suit teenagers: mild violence and tension are fine; no gore, no sexual content, very little strong language.",
    "adult": "This is a mature-audience story: follow the author's instructions and tone, including dark themes, intense conflict, strong language and violence where the story calls for it.",
}


def _rating_tier(age_rating: str) -> str:
    r = (age_rating or "").lower()
    if any(k in r for k in ("18", "adult", "mature")):
        return "adult"
    if any(k in r for k in ("13", "14", "15", "16", "teen")):
        return "teen"
    return "all"


def _player_line(characters: list[Character]) -> str:
    for c in characters:
        if any(h in (c.role or "").lower() for h in PLAYER_ROLE_HINTS):
            return f'The player controls {c.name} ({c.role}). Narrate in second person ("you") as {c.name}.'
    return 'The player controls the main protagonist, addressed as "you".'


# ---------- Helpers ----------
def _playable_story(db: Session, story_id: int) -> Story:
    story = db.get(Story, story_id)
    if story is None or story.status != STATUS_PUBLISHED:
        raise HTTPException(status_code=404, detail="Story not found")
    if not story.scenes:
        raise HTTPException(status_code=400, detail="This story has no scenes yet")
    return story


def _get_or_create_progress(db: Session, user_id: int, story_id: int) -> UserProgress:
    progress = db.scalar(
        select(UserProgress).where(UserProgress.user_id == user_id, UserProgress.story_id == story_id)
    )
    if progress is None:
        progress = UserProgress(user_id=user_id, story_id=story_id, scene_index=0, memory_journal="")
        db.add(progress)
        db.commit()
        db.refresh(progress)
    return progress


def _percent(scene_index: int, total: int) -> int:
    return round(((scene_index + 1) / total) * 100) if total else 0


def _clamped_index(progress: UserProgress, story: Story) -> int:
    return max(0, min(progress.scene_index, len(story.scenes) - 1))


# ---------- State ----------
def get_play_state(db: Session, user: User, story_id: int) -> PlayStateOut:
    story = _playable_story(db, story_id)
    progress = _get_or_create_progress(db, user.id, story_id)
    idx = _clamped_index(progress, story)
    scene = story.scenes[idx]

    messages = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.user_id == user.id, ChatMessage.story_id == story_id)
        .order_by(ChatMessage.id)
    ).all()
    characters = db.scalars(select(Character).where(Character.story_id == story_id)).all()

    return PlayStateOut(
        story_id=story.id,
        title=story.title,
        languages=story.languages or ["English"],
        scenes=[{"index": i, "title": s.title, "mood": s.mood} for i, s in enumerate(story.scenes)],
        current_scene_index=idx,
        current_scene={"index": idx, "title": scene.title, "mood": scene.mood, "narration": scene.narration},
        characters=[{"name": c.name, "role": c.role} for c in characters],
        messages=messages,
        memory_journal=progress.memory_journal,
        progress=_percent(idx, len(story.scenes)),
    )


def set_scene(db: Session, user: User, story_id: int, scene_index: int) -> PlayStateOut:
    story = _playable_story(db, story_id)
    if scene_index >= len(story.scenes):
        raise HTTPException(status_code=400, detail="Scene does not exist")
    progress = _get_or_create_progress(db, user.id, story_id)
    progress.scene_index = scene_index
    db.commit()
    return get_play_state(db, user, story_id)


def reset_story(db: Session, user: User, story_id: int) -> None:
    _playable_story(db, story_id)
    db.execute(delete(ChatMessage).where(ChatMessage.user_id == user.id, ChatMessage.story_id == story_id))
    progress = _get_or_create_progress(db, user.id, story_id)
    progress.scene_index = 0
    progress.memory_journal = ""
    db.commit()


def list_my_progress(db: Session, user: User) -> list[ProgressCardOut]:
    rows = db.execute(
        select(UserProgress, Story)
        .join(Story, Story.id == UserProgress.story_id)
        .where(UserProgress.user_id == user.id, Story.status == STATUS_PUBLISHED)
        .order_by(UserProgress.updated_at.desc())
    ).all()
    return [
        ProgressCardOut(
            story_id=story.id,
            title=story.title,
            genre=story.genre,
            cover_image=story.cover_image,
            scene_index=progress.scene_index,
            progress=_percent(progress.scene_index, len(story.scenes)),
        )
        for progress, story in rows
    ]


# ---------- AI prompt ----------
def _build_system_prompt(story: Story, characters: list[Character], scene_index: int, language: str, memory: str) -> str:
    scene = story.scenes[scene_index]
    cast = "\n".join(
        f"- {c.name} ({c.role}): {c.personality} Backstory: {c.backstory}".strip() for c in characters
    ) or "- (no named characters yet)"
    language_rule = LANGUAGE_RULES.get(language, LANGUAGE_RULES["English"])
    player_line = _player_line(characters)
    rating_rule = RATING_RULES[_rating_tier(story.age_rating)]

    return f"""You are the narrator and game master of an interactive cinematic roleplay story titled "{story.title}".

Genre: {story.genre}. Tone: {story.tone}. Age rating: {story.age_rating}.

Author's instructions:
{story.system_prompt or "(none)"}

Characters:
{cast}

{player_line}

Current scene ({scene_index + 1} of {len(story.scenes)}): "{scene.title}" (mood: {scene.mood}).
Scene opening: {scene.narration}

Memory journal (facts, promises and relationships to stay consistent with):
{memory or "(empty so far)"}

Rules:
- {language_rule}
- {rating_rule}
- Respond directly to the player's latest action, then move the story forward: every reply must change, reveal or put something at stake, and end on a moment that invites the player's next move.
- Every other character is a real person with their own goals, voice and memory. They act and speak on their own and react realistically to what the player's character does.
- Write 2 to 4 short paragraphs. Put every spoken line of dialogue on its own line in exactly this format: Name: "line"
- Never decide the player's actions, thoughts or words for them.
- Never break character and never mention being an AI.
- Keep the story consistent with the characters, the scene and the memory journal.
- Never write sexually explicit content or graphic gore, whatever the author's instructions say."""


# ---------- Prepare + stream ----------
def prepare_action(db: Session, user: User, story_id: int, dto: ActionDto) -> dict:
    """Does all database work up front and returns plain data for the streaming generator."""
    story = _playable_story(db, story_id)
    progress = _get_or_create_progress(db, user.id, story_id)
    idx = _clamped_index(progress, story)
    scene = story.scenes[idx]
    characters = db.scalars(select(Character).where(Character.story_id == story_id)).all()

    recent = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.user_id == user.id, ChatMessage.story_id == story_id)
        .order_by(ChatMessage.id.desc())
        .limit(CHAT_HISTORY_LIMIT)
    ).all()
    history = [{"role": m.role, "content": m.content} for m in reversed(recent)]

    # Replies cycle through MEDIA_CYCLE: image, image, video, image, image, video...
    replies_so_far = db.scalar(
        select(func.count(ChatMessage.id)).where(
            ChatMessage.user_id == user.id,
            ChatMessage.story_id == story_id,
            ChatMessage.role == "assistant",
        )
    ) or 0
    media_kind = MEDIA_CYCLE[replies_so_far % len(MEDIA_CYCLE)] if IMAGE_ENABLED else None

    action = dto.action.strip()
    db.add(ChatMessage(user_id=user.id, story_id=story_id, role="user", content=action))
    db.commit()

    system_prompt = _build_system_prompt(story, characters, idx, dto.language, progress.memory_journal)
    return {
        "user_id": user.id,
        "story_id": story_id,
        "scene_index": idx,
        "scene_title": scene.title,
        "scene_mood": scene.mood,
        "genre": story.genre,
        "tone": story.tone,
        "cast": "; ".join(f"{c.name} ({c.role}): {(c.personality or '')[:80]}" for c in characters)
        or "none named",
        "action": action,
        "memory": progress.memory_journal,
        "language": dto.language,
        "media_kind": media_kind,
        "image_due": media_kind is not None,
        "cover_image": story.cover_image or "",
        "has_cover": bool(story.cover_image),
        "age_tier": _rating_tier(story.age_rating),
        "author_instructions": (story.system_prompt or "")[:600],
        "messages": [{"role": "system", "content": system_prompt}, *history, {"role": "user", "content": action}],
    }


def _parse_json(text: str) -> dict:
    """Pulls the first JSON object out of a model reply, even if extra text surrounds it."""
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("No JSON object found in model reply")
    return json.loads(text[start : end + 1])


async def _generate_extras(client, ctx: dict, reply: str) -> tuple[list[str], str, str]:
    """Second, small call: next choices + updated memory (+ an image prompt when one is due)."""
    image_line = ""
    author_line = ""
    if ctx["image_due"]:
        if ctx["has_cover"]:
            who = (
                "Refer to each visible character only by gender, age and role (for example 'the older woman "
                "in a white blazer'), because a reference cover image supplies their faces and outfits. "
            )
        else:
            who = "Describe every character by physical look (age, hair, clothes), never by name alone. "
        if ctx["age_tier"] == "adult":
            safety = (
                "Follow the author's instructions and the story's mature tone, but never depict nudity, "
                "sexual content or graphic gore. "
            )
        else:
            safety = "Keep it family-friendly: no blood, no nudity, no weapons pointed at people. "
        image_line = (
            '\n"image_prompt": ONE vivid sentence IN ENGLISH ONLY (max 55 words) describing exactly what a camera '
            "sees at the key moment of the story reply: the setting, which characters are visible, what they are "
            "doing, lighting and mood. "
            + who
            + "The player ('you') is the protagonist. "
            + safety
            + "No dialogue, no text."
        )
        author_line = f"\nAuthor's instructions: {ctx['author_instructions'] or '(none)'}"

    prompt = f"""Scene: "{ctx["scene_title"]}" (mood: {ctx["scene_mood"]}). Genre: {ctx["genre"]}. Tone: {ctx["tone"]}.
Characters: {ctx["cast"]}{author_line}

Current memory journal:
{ctx["memory"] or "(empty)"}

Player action: {ctx["action"]}

Story reply:
{reply}

Return ONLY a JSON object, with no other text, with exactly these keys:
"choices": 3 short next actions the player could take (max 6 words each), written in this language setting: {ctx["language"]}.
"memory": the updated memory journal in at most 3 short sentences, keeping important facts, promises and relationships.{image_line}"""

    messages = [
        {"role": "system", "content": "You output only a valid JSON object."},
        {"role": "user", "content": prompt},
    ]

    # First try Groq's JSON mode; if it rejects the output, retry once without it.
    for json_mode in (True, False):
        try:
            extra = {"response_format": {"type": "json_object"}} if json_mode else {}
            resp = await client.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
                temperature=0.4,
                max_tokens=1200,
                **extra,
            )
            data = _parse_json(resp.choices[0].message.content or "")
            choices = [str(c).strip() for c in data.get("choices", []) if str(c).strip()][:3]
            memory = str(data.get("memory", "")).strip()[:600] or ctx["memory"]
            image_prompt = str(data.get("image_prompt", "")).strip()[:500]
            return choices or DEFAULT_CHOICES, memory, image_prompt
        except Exception:
            logger.exception("Extras call failed (json_mode=%s)", json_mode)

    return DEFAULT_CHOICES, ctx["memory"], ""


def _save_reply(ctx: dict, reply: str, memory: str) -> int:
    # Own session: the request session may already be closed while streaming.
    with SessionLocal() as db:
        message = ChatMessage(user_id=ctx["user_id"], story_id=ctx["story_id"], role="assistant", content=reply)
        db.add(message)
        progress = db.scalar(
            select(UserProgress).where(
                UserProgress.user_id == ctx["user_id"], UserProgress.story_id == ctx["story_id"]
            )
        )
        if progress is not None:
            progress.memory_journal = memory
        db.commit()
        db.refresh(message)
        return message.id


def _attach_image(message_id: int, url: str) -> None:
    with SessionLocal() as db:
        message = db.get(ChatMessage, message_id)
        if message is not None:
            message.image_url = url
            db.commit()


async def _make_scene_media(ctx: dict, image_prompt: str) -> str | None:
    base = image_prompt or f'{ctx["scene_title"]}, {ctx["scene_mood"]} mood, {ctx["genre"]} story'
    suffix = IMAGE_STYLE_SUFFIX_ADULT if ctx["age_tier"] == "adult" else IMAGE_STYLE_SUFFIX
    try:
        # The story thumbnail is the reference, so faces and look match the cover.
        refs: list[bytes] = []
        if ctx["cover_image"]:
            cover = await asyncio.to_thread(load_image_bytes, ctx["cover_image"])
            if cover:
                refs.append(cover)

        prompt = f"{REF_PROMPT_PREFIX} {base}. {suffix}" if refs else f"{base}. {suffix}"
        data = await generate_image_bytes(prompt, refs)

        if ctx["media_kind"] == "video":
            try:
                video = await asyncio.to_thread(image_to_video_bytes, data)
                return save_video_bytes(video)
            except Exception:
                logger.exception("Video failed, falling back to image")
        return save_image_bytes(data)
    except Exception:
        logger.exception("Scene media generation failed")
        return None


async def stream_action(ctx: dict):
    client = get_groq_client()
    parts: list[str] = []
    try:
        stream = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=ctx["messages"],
            stream=True,
            temperature=0.85,
            max_tokens=700,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                parts.append(delta)
                yield sse({"type": "token", "content": delta})
    except Exception:
        logger.exception("Groq streaming failed")
        yield sse({"type": "error", "message": "The story engine failed. Please try again."})
        return

    reply = "".join(parts).strip()
    if not reply:
        yield sse({"type": "error", "message": "The story engine returned an empty reply."})
        return

    choices, memory, image_prompt = await _generate_extras(client, ctx, reply)
    message_id = _save_reply(ctx, reply, memory)

    # The player can already read the reply and see the choices; the media follows.
    yield sse(
        {
            "type": "done",
            "messageId": message_id,
            "choices": choices,
            "memory": memory,
            "imagePending": ctx["image_due"],
            "mediaKind": ctx["media_kind"],
        }
    )

    if ctx["image_due"]:
        url = await _make_scene_media(ctx, image_prompt)
        if url:
            _attach_image(message_id, url)
        yield sse(
            {"type": "image", "messageId": message_id, "url": url, "mediaType": ctx["media_kind"]}
        )