from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from src.play import controller
from src.play.dtos import ActionDto, PlayStateOut, ProgressCardOut, SceneUpdateDto
from src.users.model import User
from src.utils.db import get_db
from src.utils.helper import get_current_user, get_groq_client

router = APIRouter(prefix="/play", tags=["Play"])


# Declared first so "progress" is not parsed as a story_id.
@router.get("/progress/me", response_model=list[ProgressCardOut])
def my_progress(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return controller.list_my_progress(db, user)


@router.get("/{story_id}", response_model=PlayStateOut)
def play_state(story_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return controller.get_play_state(db, user, story_id)


@router.put("/{story_id}/scene", response_model=PlayStateOut)
def change_scene(
    story_id: int,
    dto: SceneUpdateDto,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return controller.set_scene(db, user, story_id, dto.scene_index)


@router.post("/{story_id}/action")
def play_action(
    story_id: int,
    dto: ActionDto,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_groq_client()  # fails early if the API key is missing
    ctx = controller.prepare_action(db, user, story_id, dto)
    return StreamingResponse(
        controller.stream_action(ctx),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{story_id}/reset", status_code=204)
def reset(story_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    controller.reset_story(db, user, story_id)
    return Response(status_code=204)