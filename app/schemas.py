from pydantic import BaseModel
from datetime import date
class UserCreate(BaseModel):
    email: str
    name: str
    preferred_name: str
    username: str
    password: str  # plain password, hashed server-side

class UserLogin(BaseModel):
    email: str
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