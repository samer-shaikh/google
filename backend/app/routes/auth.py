from fastapi import APIRouter, Request
from app.core.exceptions import ConflictException,BadRequestException,ForbiddenException,UnauthorizedException
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config

from fastapi import Depends
from sqlalchemy.orm import Session
from datetime import timedelta
from app.schemas.auth import RefreshRequest,SignupRequest,LoginRequest

from app.database import SessionLocal
from app.models.user import User
from app.core.security import hash_password, verify_password, create_token
from app.core.security import ACCESS_TOKEN_EXPIRE_MINUTES,REFRESH_TOKEN_EXPIRE_DAYS,SECRET_KEY,ALGORITHM
from app.database import get_db
from app.dependencies.auth import get_current_user

from jose import jwt, JWTError, ExpiredSignatureError
import os






router = APIRouter(prefix="/auth", tags=["auth"])

config = Config(".env")

oauth = OAuth(config)

oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url=
    "https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid email profile"
    }
)

#=================================== google login =====================================

@router.get("/google/login")
async def googl_login(request: Request):

    redirect_uri = request.url_for("auth_callback")
    print("REDIRECT URI =", redirect_uri)
    return await oauth.google.authorize_redirect(
        request,
        redirect_uri
    )

@router.get("/google/callback", name="auth_callback")
async def auth_callback(
    request: Request,
    db: Session = Depends(get_db)
):

    token = await oauth.google.authorize_access_token(
        request
    )

    user_info = token.get("userinfo")

    email = user_info["email"]

    existing_user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    if not existing_user:

        new_user = User(
            email=user_info["email"],
            google_id=user_info["sub"],
            name=user_info["name"],
            picture=user_info["picture"]
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        existing_user = new_user

    access_token = create_token(
        {
            "sub": existing_user.email,
            "type": "access"
        },
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    refresh_token = create_token(
        {
            "sub": existing_user.email,
            "type": "refresh"
        },
        timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": existing_user.id,
            "email": existing_user.email,
            "name": existing_user.name
        }
    }
#==================================== normal login =========================================

@router.post("/signup")
def signup(
    data: SignupRequest,
    db: Session = Depends(get_db)
):
    existing = db.query(User).filter(
        User.email == data.email
    ).first()

    if existing:
        return {"error": "email already exists"}

    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        name=data.name
    )

    db.add(user)
    db.commit()

    return {"message": "user created"}



@router.post("/login")
def login(
    data: LoginRequest,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(
        User.email == data.email
    ).first()

    if not user:
        return {"error": "Email not found"}

    if not verify_password(
        data.password,
        user.password_hash
    ):
        return {"error": "Wrong password"}

    access_token = create_token(
        {
            "sub": user.email,
            "type": "access"
        },
        timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
    )

    refresh_token = create_token(
        {
            "sub": user.email,
            "type": "refresh"
        },
        timedelta(
            days=REFRESH_TOKEN_EXPIRE_DAYS
        )
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name
        }
    }



@router.post("/refresh")
def refresh_token(data: RefreshRequest):

    try:
        payload = jwt.decode(
            data.refresh_token,
            SECRET_KEY, # type: ignore
            algorithms=[ALGORITHM] # type: ignore
        )

    except ExpiredSignatureError:
        raise UnauthorizedException("Refresh token expired")

    except JWTError:
        raise UnauthorizedException("Invalid refresh token")

    if payload.get("type") != "refresh":
        raise ForbiddenException("Invalid token type")

    email = payload.get("sub")

    if not email:
        raise UnauthorizedException("Invalid token payload")

    new_access_token = create_token(
        {
            "sub": email,
            "type": "access"
        },
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    return {
        "access_token": new_access_token,
        "token_type": "bearer"
    }

@router.get("/me")
def get_me(
    current_user: User = Depends(get_current_user)
):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name
    }