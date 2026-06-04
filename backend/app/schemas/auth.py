from pydantic import BaseModel

class RefreshRequest(BaseModel):
    refresh_token: str


class SignupRequest(BaseModel):
    email: str
    password: str
    name: str


class LoginRequest(BaseModel):
    email: str
    password: str