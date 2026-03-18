from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import SessionLocal, engine
from app.auth import hash_password, verify_password, create_access_token, get_current_user
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
import os
from dotenv import load_dotenv
import random
import datetime
from fastapi.middleware.cors import CORSMiddleware
import requests
from fastapi import Header

load_dotenv(dotenv_path="/Users/abel/Desktop/TemanU-backend/.env")

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows any web port to connect during local testing
    allow_credentials=True,
    allow_methods=["*"],  # Allows POST, GET, OPTIONS, etc.
    allow_headers=["*"],  # Allows all headers (like your Authorization JWT)
)

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
        password_hash= hash_password(user.password),
        gender=user.gender,
        dob=user.dob,
        blood_type=user.blood_type,
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
    return {
        "access_token": token, 
        "token_type": "bearer",
        "name": user.preferred_name, 
        "email": user.email,
        "full_name": user.name,
        "username": user.username
    }

    
@app.post("/login")
def login(credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    print("\n--- NEW LOGIN ATTEMPT ---")
    print(f"Username typed: '{credentials.username}'")
    
    user = db.query(models.User).filter(models.User.username == credentials.username).first()
    
    if not user:
        print("❌ REJECTED: That username does not exist in the database.")
        raise HTTPException(status_code=401, detail="Invalid username or password")
        
    if not verify_password(credentials.password, user.password_hash):
        print("❌ REJECTED: The password does not match the saved hash.")
        raise HTTPException(status_code=401, detail="Invalid username or password")
        
    print("✅ SUCCESS: Passwords match, logging user in!")
    token = create_access_token(data={"sub": str(user.id)})
    
    return {
        "access_token": token, 
        "token_type": "bearer",
        "name": user.preferred_name, 
        "email": user.email,
        "full_name": user.name,
        "username": user.username
    }

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

# Health APIs
@app.post("/health", response_model=schemas.HealthMetricOut)
def create_health_metric(
    metric: schemas.HealthMetricCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user) 
):
    new_metric = models.HealthMetric(
        user_id=current_user.id, 
        metric_type=metric.metric_type,
        value=metric.value,
        unit=metric.unit
    )

    db.add(new_metric)
    db.commit()
    db.refresh(new_metric)

    return new_metric

@app.get("/health", response_model=list[schemas.HealthMetricOut])
def get_health_metrics(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    metrics = db.query(models.HealthMetric).filter(
        models.HealthMetric.user_id == current_user.id
    ).all()

    return metrics

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

import random

@app.post("/forgot-password")
async def forgot_password(request: schemas.RequestOTP, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == request.email).first()
    if not user:
        return {"message": "If that email exists, an OTP has been sent"}

    # Generate 6 digit OTP
    code = str(random.randint(100000, 999999))
    expires_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=15)

    # Delete any existing OTP for this email
    db.query(models.OTPCode).filter(models.OTPCode.email == request.email).delete()

    # Save new OTP
    otp = models.OTPCode(email=request.email, code=code, expires_at=expires_at)
    db.add(otp)
    db.commit()

    # Send email
    message = MessageSchema(
        subject="TemanU Password Reset OTP",
        recipients=[user.email],
        body=f"Hi {user.preferred_name},\n\nYour password reset code is: {code}\n\nThis code expires in 15 minutes.\n\nIf you did not request this, ignore this email.",
        subtype="plain"
    )
    fm = FastMail(mail_config)
    await fm.send_message(message)

    return {"message": "If that email exists, an OTP has been sent"}

@app.post("/reset-password")
def reset_password(request: schemas.VerifyOTP, db: Session = Depends(get_db)):
    otp = db.query(models.OTPCode).filter(
        models.OTPCode.email == request.email,
        models.OTPCode.code == request.code
    ).first()

    if not otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    if otp.expires_at < datetime.datetime.utcnow():
        db.delete(otp)
        db.commit()
        raise HTTPException(status_code=400, detail="OTP has expired")

    user = db.query(models.User).filter(models.User.email == request.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password_hash = hash_password(request.new_password)
    db.delete(otp)
    db.commit()

    return {"message": "Password updated successfully"}


@app.post("/change-password/request-otp")
async def request_change_password_otp(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Generate OTP
    code = str(random.randint(100000, 999999))
    expires_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=15)

    # Delete any existing OTP for this user
    db.query(models.OTPCode).filter(models.OTPCode.email == current_user.email).delete()

    # Save new OTP
    otp = models.OTPCode(email=current_user.email, code=code, expires_at=expires_at)
    db.add(otp)
    db.commit()

    # Send email
    message = MessageSchema(
        subject="TemanU Password Change OTP",
        recipients=[current_user.email],
        body=f"Hi {current_user.preferred_name},\n\nYour password change code is: {code}\n\nThis code expires in 15 minutes.\n\nIf you did not request this, please secure your account immediately.",
        subtype="plain"
    )
    fm = FastMail(mail_config)
    await fm.send_message(message)

    return {"message": "OTP sent to your registered email"}


@app.post("/change-password/verify")
def verify_change_password(
    request: schemas.VerifyChangePassword,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    otp = db.query(models.OTPCode).filter(
        models.OTPCode.email == current_user.email,
        models.OTPCode.code == request.code
    ).first()

    if not otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    if otp.expires_at < datetime.datetime.utcnow():
        db.delete(otp)
        db.commit()
        raise HTTPException(status_code=400, detail="OTP has expired")

    db_user = db.query(models.User).filter(models.User.email == current_user.email).first()
    db_user.password_hash = hash_password(request.new_password)
    
    db.delete(otp)
    db.commit()

    return {"message": "Password changed successfully"}

@app.get("/fitbit/activity/{date}")
def get_fitbit_activity(date: str, fitbit_token: str = Header(None)):
    # 1. Make sure the Flutter app actually sent the Fitbit token
    if not fitbit_token:
        raise HTTPException(status_code=400, detail="Fitbit token missing")

    # 2. Build the exact Fitbit URL you were trying to reach earlier
    url = f"https://api.fitbit.com/1/user/-/activities/date/{date}.json"
    
    # 3. Attach the token to the header exactly how Fitbit expects it
    headers = {"Authorization": f"Bearer {fitbit_token}"}

    # 4. Have Python make the request (Bypasses CORS entirely!)
    response = requests.get(url, headers=headers)

    # 5. If Fitbit gets mad (e.g., expired token), tell the Flutter app
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Fitbit API error")

    # 6. Return the raw Fitbit JSON back to Flutter
    return response.json()