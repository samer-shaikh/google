from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import jwt, JWTError, ExpiredSignatureError

from app.database import get_db
from app.models.user import User

from app.core.security import SECRET_KEY, ALGORITHM
from app.core.exceptions import (
    UnauthorizedException,
    ForbiddenException
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

    except ExpiredSignatureError:
        raise UnauthorizedException("Access token expired")

    except JWTError:
        raise UnauthorizedException("Invalid token")

    if payload.get("type") != "access":
        raise ForbiddenException("Invalid token type")

    email = payload.get("sub")

    if not email:
        raise UnauthorizedException("Invalid token payload")

    user = db.query(User).filter(
        User.email == email
    ).first()

    if not user:
        raise UnauthorizedException("User not found")

    return user