from fastapi import Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from jose import jwt, JWTError, ExpiredSignatureError

from app.database import get_db
from app.models.user import User
from app.core.security import SECRET_KEY, ALGORITHM
from app.core.exceptions import UnauthorizedException, ForbiddenException

# HTTPBearer reads the  Authorization: Bearer <token>  header directly.
# This is what makes the Swagger UI lock icon work correctly — the
# OAuth2PasswordBearer scheme that was here before expected a form-based
# username/password flow, which is why Swagger showed a broken popup.
_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Extract and validate the JWT from the Authorization header.
    Works in Swagger UI after clicking Authorize and pasting the access_token.
    """
    if credentials is None:
        raise UnauthorizedException("Missing Authorization header")

    token = credentials.credentials

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

    except ExpiredSignatureError:
        raise UnauthorizedException("Access token expired")

    except JWTError:
        raise UnauthorizedException("Invalid token")

    if payload.get("type") != "access":
        raise ForbiddenException("Invalid token type")

    email = payload.get("sub")
    if not email:
        raise UnauthorizedException("Invalid token payload")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise UnauthorizedException("User not found")

    return user
