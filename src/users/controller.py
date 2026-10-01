from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.play.model import UserProgress
from src.users.dtos import AdminUserOut, LoginDto, SignupDto, TokenOut, UserOut
from src.users.model import User
from src.utils.constant import ADMIN_EMAIL, ADMIN_NAME, ADMIN_PASSWORD, ROLE_ADMIN, ROLE_USER
from src.utils.helper import create_access_token, hash_password, verify_password


def _token_response(user: User) -> TokenOut:
    return TokenOut(
        access_token=create_access_token(user.id, user.role),
        user=UserOut.model_validate(user),
    )


def signup(dto: SignupDto, db: Session) -> TokenOut:
    email = dto.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(
        name=dto.name.strip(),
        email=email,
        password_hash=hash_password(dto.password),
        role=ROLE_USER,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _token_response(user)


def login(dto: LoginDto, db: Session) -> TokenOut:
    user = db.scalar(select(User).where(User.email == dto.email.lower()))
    if user is None or not verify_password(dto.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    return _token_response(user)


def list_users(db: Session) -> list[AdminUserOut]:
    counts = dict(
        db.execute(
            select(UserProgress.user_id, func.count(UserProgress.id)).group_by(UserProgress.user_id)
        ).all()
    )
    users = db.scalars(select(User).order_by(User.created_at.desc())).all()
    return [
        AdminUserOut(
            id=u.id,
            name=u.name,
            email=u.email,
            role=u.role,
            created_at=u.created_at,
            stories_played=counts.get(u.id, 0),
        )
        for u in users
    ]


def seed_admin(db: Session) -> None:
    """Creates the first admin from .env if it does not exist yet."""
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        return
    email = ADMIN_EMAIL.lower()
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        if existing.role != ROLE_ADMIN:
            existing.role = ROLE_ADMIN
            db.commit()
        return
    db.add(
        User(
            name=ADMIN_NAME,
            email=email,
            password_hash=hash_password(ADMIN_PASSWORD),
            role=ROLE_ADMIN,
        )
    )
    db.commit()