from pydantic import BaseModel
from datetime import date
class UserCreate(BaseModel):
    email: str
    name: str
    preferred_name: str
    username: str
    password: str  # plain password, hashed server-side

class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    preferred_name: str
    username: str

    class Config:
        from_attributes = True

# ===== Activity Schemas =====
class ActivityCreate(BaseModel):
    user_id: int
    steps: int
    date: date

class ActivityOut(BaseModel):
    id: int
    user_id: int
    steps: int
    date: date

    class Config:
        from_attributes = True

#password resets~


class RequestOTP(BaseModel):
    email: str

class VerifyOTP(BaseModel):
    email: str
    code: str
    new_password: str


class RequestChangePasswordOTP(BaseModel):
    pass  # no fields needed we get email from token

class VerifyChangePassword(BaseModel):
    code: str
    new_password: str