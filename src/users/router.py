from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.users import controller
from src.users.dtos import AdminUserOut, LoginDto, SignupDto, TokenOut, UserOut
from src.users.model import User
from src.utils.db import get_db
from src.utils.helper import get_current_user, require_admin

router = APIRouter(prefix="/auth", tags=["Auth"])
admin_router = APIRouter(prefix="/admin/users", tags=["Admin · Users"], dependencies=[Depends(require_admin)])


@router.post("/signup", response_model=TokenOut, status_code=201)
def signup(dto: SignupDto, db: Session = Depends(get_db)):
    return controller.signup(dto, db)


@router.post("/login", response_model=TokenOut)
def login(dto: LoginDto, db: Session = Depends(get_db)):
    return controller.login(dto, db)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@admin_router.get("", response_model=list[AdminUserOut])
def list_users(db: Session = Depends(get_db)):
    return controller.list_users(db)