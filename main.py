from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import SessionLocal, engine
from app.auth import hash_password, verify_password, create_access_token, get_current_user, create_reset_token, verify_reset_token
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
import os
from dotenv import load_dotenv


load_dotenv(dotenv_path="/Users/abel/Desktop/TemanU-backend/.env")

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

def get_db():
    database = SessionLocal()
    try:
        yield database
    finally:
        database.close()

@app.post("/register")
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    # Check if email or username already exists
    if db.query(models.User).filter(models.User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    if db.query(models.User).filter(models.User.username == user.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")

    new_user = models.User(
        email=user.email,
        name=user.name,
        preferred_name=user.preferred_name,
        username=user.username,
        password_hash= hash_password(user.password)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "User created successfully", "id": new_user.id}

@app.post("/login")
def login(credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == credentials.username).first()
    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token(data={"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}

    
@app.post("/login/swagger")
def swagger_login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(data={"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}    

# Example protected route — requires a valid JWT
@app.get("/me", response_model=schemas.UserOut)
def get_me(current_user: models.User = Depends(get_current_user)):
    return current_user

# Activity APIs
@app.post("/activity", response_model=schemas.ActivityOut)
def create_activity(
    activity: schemas.ActivityCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):

    new_activity = models.Activity(
        user_id=current_user.id, # Always use token users
        steps=activity.steps,
        date=activity.date
    )

    db.add(new_activity)
    db.commit()
    db.refresh(new_activity)

    return new_activity


@app.get("/activity", response_model=list[schemas.ActivityOut])
def get_activity(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):

    activities = db.query(models.Activity).filter(
        models.Activity.user_id == current_user.id
    ).all()

    return activities


mail_config = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_EMAIL"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
    MAIL_FROM=os.getenv("MAIL_EMAIL"),
    MAIL_PORT=587,
    MAIL_SERVER="smtp.gmail.com",
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True
)

@app.post("/forgot-password")
async def forgot_password(request: schemas.ForgotPassword, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == request.email).first()
    if not user:
        return {"message": "If that email exists, a reset link has been sent"}
    
    token = create_reset_token(user.email)
    reset_link = f"http://localhost:8000/reset-password?token={token}"

    message = MessageSchema(
        subject="TemanU Password Reset",
        recipients=[user.email],
        body=f"Hi {user.preferred_name},\n\nClick the link below to reset your password. This link expires in 15 minutes.\n\n{reset_link}\n\nIf you did not request this, ignore this email.",
        subtype="plain"
    )

    fm = FastMail(mail_config)
    await fm.send_message(message)

    return {"message": "If that email exists, a reset link has been sent"}

@app.post("/reset-password")
def reset_password(request: schemas.ResetPassword, db: Session = Depends(get_db)):
    email = verify_reset_token(request.token)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password_hash = hash_password(request.new_password)
    db.commit()

    return {"message": "Password updated successfully"}