import json
import logging

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.characters.model import Character
from src.play.dtos import ActionDto, ProgressCardOut, PlayStateOut
from src.play.model import ChatMessage, UserProgress
from src.stories.model import Story
from src.users.model import User
from src.utils.constant import (
    CHAT_HISTORY_LIMIT,
    DEFAULT_CHOICES,
    GROQ_MODEL,
    LANGUAGE_RULES,
    STATUS_PUBLISHED,
)
from src.utils.db import SessionLocal
from src.utils.helper import get_groq_client, sse

logger = logging.getLogger("velune.play")


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

    return f"""You are the narrator and game master of an interactive cinematic roleplay story titled "{story.title}".

Genre: {story.genre}. Tone: {story.tone}. Age rating: {story.age_rating}.

Author's instructions:
{story.system_prompt or "(none)"}

Characters:
{cast}

Current scene ({scene_index + 1} of {len(story.scenes)}): "{scene.title}" (mood: {scene.mood}).
Scene opening: {scene.narration}

Memory journal (facts, promises and relationships to stay consistent with):
{memory or "(empty so far)"}

Rules:
- {language_rule}
- Narrate in second person ("you"). Respond directly to the player's latest action.
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
    characters = db.scalars(select(Character).where(Character.story_id == story_id)).all()

    recent = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.user_id == user.id, ChatMessage.story_id == story_id)
        .order_by(ChatMessage.id.desc())
        .limit(CHAT_HISTORY_LIMIT)
    ).all()
    history = [{"role": m.role, "content": m.content} for m in reversed(recent)]

    action = dto.action.strip()
    db.add(ChatMessage(user_id=user.id, story_id=story_id, role="user", content=action))
    db.commit()

    system_prompt = _build_system_prompt(story, characters, idx, dto.language, progress.memory_journal)
    return {
        "user_id": user.id,
        "story_id": story_id,
        "scene_index": idx,
        "action": action,
        "memory": progress.memory_journal,
        "language": dto.language,
        "messages": [{"role": "system", "content": system_prompt}, *history, {"role": "user", "content": action}],
    }


async def _generate_extras(client, ctx: dict, reply: str) -> tuple[list[str], str]:
    """Second, small call: next choices + updated memory journal as JSON."""
    prompt = f"""Current memory journal:
{ctx["memory"] or "(empty)"}

Player action: {ctx["action"]}

Story reply:
{reply}

Return JSON with exactly these keys:
"choices": 3 short next actions the player could take (max 6 words each), written in this language setting: {ctx["language"]}.
"memory": the updated memory journal in at most 3 short sentences, keeping important facts, promises and relationships."""
    try:
        resp = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": "You output only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
            max_tokens=300,
        )
        data = json.loads(resp.choices[0].message.content)
        choices = [str(c).strip() for c in data.get("choices", []) if str(c).strip()][:3]
        memory = str(data.get("memory", "")).strip()[:600] or ctx["memory"]
        return choices or DEFAULT_CHOICES, memory
    except Exception:
        logger.exception("Could not generate choices/memory")
        return DEFAULT_CHOICES, ctx["memory"]


def _save_reply(ctx: dict, reply: str, memory: str) -> None:
    # Own session: the request session may already be closed while streaming.
    with SessionLocal() as db:
        db.add(ChatMessage(user_id=ctx["user_id"], story_id=ctx["story_id"], role="assistant", content=reply))
        progress = db.scalar(
            select(UserProgress).where(
                UserProgress.user_id == ctx["user_id"], UserProgress.story_id == ctx["story_id"]
            )
        )
        if progress is not None:
            progress.memory_journal = memory
        db.commit()


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

    choices, memory = await _generate_extras(client, ctx, reply)
    _save_reply(ctx, reply, memory)
    yield sse({"type": "done", "choices": choices, "memory": memory})