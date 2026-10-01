import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.utils.constant import FRONTEND_ORIGINS, UPLOAD_DIR
from src.utils.db import Base, SessionLocal, engine

# Importing the routers also imports every model, so create_all sees all tables.
from src.characters.router import admin_router as characters_admin_router
from src.characters.router import router as characters_router
from src.play.router import router as play_router
from src.stories.router import admin_router as stories_admin_router
from src.stories.router import router as stories_router
from src.stories.router import stats_router
from src.uploads.router import router as uploads_router
from src.users.controller import seed_admin
from src.users.router import admin_router as users_admin_router
from src.users.router import router as auth_router

os.makedirs(UPLOAD_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_admin(db)
    yield


app = FastAPI(title="VELUNE API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(users_admin_router)
app.include_router(stories_router)
app.include_router(stories_admin_router)
app.include_router(stats_router)
app.include_router(characters_router)
app.include_router(characters_admin_router)
app.include_router(play_router)
app.include_router(uploads_router)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/", tags=["Health"])
def health():
    return {"status": "ok", "app": "VELUNE API"}