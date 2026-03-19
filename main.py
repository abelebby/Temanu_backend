from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func
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

load_dotenv()

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

# Example protected route — requires a valid JWT
@app.get("/me", response_model=schemas.UserOut)
def get_me(current_user: models.User = Depends(get_current_user)):
    return current_user

@app.delete("/users/me")
def delete_account(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 1. Sweep up all health metrics associated with this user
    db.query(models.HealthMetric).filter(models.HealthMetric.user_id == current_user.id).delete()

    # 2. Sweep up all activity metrics
    db.query(models.Activity).filter(models.Activity.user_id == current_user.id).delete()

    # 3. Delete any lingering OTP codes for their email
    db.query(models.OTPCode).filter(models.OTPCode.email == current_user.email).delete()

    # 4. --- THE FIX: Delete the user using the CURRENT session! ---
    db.query(models.User).filter(models.User.id == current_user.id).delete()
    db.commit()
    # ---------------------------------------------------------------

    return {"message": "Account and all associated data successfully deleted"}

@app.post("/fitbit/link")
def link_fitbit_account(
    tokens: schemas.FitbitTokenSave,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 1. Check if this user already has a linked Fitbit account
    existing_link = db.query(models.FitbitToken).filter(models.FitbitToken.user_id == current_user.id).first()
    
    if existing_link:
        # Update existing tokens
        existing_link.access_token = tokens.access_token
        existing_link.refresh_token = tokens.refresh_token
    else:
        # Create a brand new link
        new_link = models.FitbitToken(
            user_id=current_user.id,
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token
        )
        db.add(new_link)
        
    db.commit()
    return {"message": "Fitbit successfully linked to your account!"}

# Activity APIs
@app.get("/fitbit/activity/{date}")
def get_fitbit_activity(
    date: str, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 1. Look up the token in our new dedicated table
    fitbit_data = db.query(models.FitbitToken).filter(models.FitbitToken.user_id == current_user.id).first()
    
    if not fitbit_data or not fitbit_data.access_token:
        raise HTTPException(status_code=400, detail="Fitbit account not linked")

    # 2. Fetch the data using their secure database token
    url = f"https://api.fitbit.com/1/user/-/activities/date/{date}.json"
    headers = {"Authorization": f"Bearer {fitbit_data.access_token}"}
    response = requests.get(url, headers=headers)

    # 3. Handle expired tokens by wiping the row so they can reconnect
    if response.status_code == 401:
        db.delete(fitbit_data)
        db.commit()
        raise HTTPException(status_code=401, detail="Fitbit token expired. Please reconnect.")
        
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Fitbit API error")

    return response.json()

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
        blood_glucose=metric.blood_glucose,
        heart_rate=metric.heart_rate,
        oxygen_saturation=metric.oxygen_saturation,
        blood_pressure_systolic=metric.blood_pressure_systolic,
        blood_pressure_diastolic=metric.blood_pressure_diastolic,
        calories=metric.calories,
        body_weight=metric.body_weight
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
    # Retrieve the user's health history ordered by the newest readings first
    metrics = db.query(models.HealthMetric).filter(
        models.HealthMetric.user_id == current_user.id
    ).order_by(models.HealthMetric.timestamp.desc()).all()

    return metrics

# This endpoint is specifically for the Flutter app's dashboard to quickly fetch the latest health metric for charting
@app.get("/health/latest", response_model=schemas.HealthMetricOut)
def get_latest_health_metric(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Query the database for the current user's health metrics
    # Order them descending by timestamp (newest first) and grab the very first one
    latest_metric = db.query(models.HealthMetric).filter(
        models.HealthMetric.user_id == current_user.id
    ).order_by(models.HealthMetric.timestamp.desc()).first()

    # If the user hasn't logged any health data yet, return a 404 Not Found
    if not latest_metric:
        raise HTTPException(status_code=404, detail="No health data found for this user")

    return latest_metric

# Password Reset APIs
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
# Endpoint to request password reset OTP
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

@app.post("/meals", response_model=schemas.MealOut)
def log_meal(
    meal: schemas.MealCreate, 
    db: Session = Depends(get_db), 
    current_user: models.User = Depends(get_current_user)
):
    new_meal = models.MealLog(
        user_id=current_user.id,
        name=meal.name,
        calories=meal.calories,
        protein=meal.protein,
        carbs=meal.carbs,
        fats=meal.fats
    )
    
    db.add(new_meal)
    db.commit()
    db.refresh(new_meal)
    return new_meal

@app.get("/meals/today", response_model=list[schemas.MealOut])
def get_todays_meals(
    db: Session = Depends(get_db), 
    current_user: models.User = Depends(get_current_user)
):
    # Ask the database for all meals matching the current user, where the timestamp date is today
    today = datetime.date.today()
    
    meals = db.query(models.MealLog).filter(
        models.MealLog.user_id == current_user.id,
        func.date(models.MealLog.timestamp) == today
    ).all()
    
    return meals

@app.get("/insights/weekly")
def get_weekly_insights(
    db: Session = Depends(get_db), 
    current_user: models.User = Depends(get_current_user)
):
    today = datetime.date.today()
    seven_days_ago = today - datetime.timedelta(days=6) # Get the last 7 days inclusive

    # 1. Grab 7 days of Meals and group them by date
    meals = db.query(
        func.date(models.MealLog.timestamp).label("date"),
        func.sum(models.MealLog.calories).label("calories"),
        func.sum(models.MealLog.protein).label("protein"),
        func.sum(models.MealLog.carbs).label("carbs"),
        func.sum(models.MealLog.fats).label("fats")
    ).filter(
        models.MealLog.user_id == current_user.id,
        func.date(models.MealLog.timestamp) >= seven_days_ago
    ).group_by(func.date(models.MealLog.timestamp)).all()

    # Convert to a dictionary for easy lookup: {"2026-03-15": {"calories": 2000...}}
    meal_dict = {
        str(m.date): {
            "consumed": m.calories or 0, 
            "protein": m.protein or 0, 
            "carbs": m.carbs or 0, 
            "fats": m.fats or 0
        } for m in meals
    }

    # 2. Grab 7 days of Fitbit Burn data (if linked)
    fitbit_data = db.query(models.FitbitToken).filter(models.FitbitToken.user_id == current_user.id).first()
    fitbit_dict = {}
    
    if fitbit_data and fitbit_data.access_token:
        # Use Fitbit's Time Series API to get a whole week at once!
        url = f"https://api.fitbit.com/1/user/-/activities/calories/date/{seven_days_ago}/{today}.json"
        headers = {"Authorization": f"Bearer {fitbit_data.access_token}"}
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            fb_json = response.json()
            for item in fb_json.get("activities-calories", []):
                fitbit_dict[item["dateTime"]] = float(item["value"])

    # 3. Merge them together into a perfect 7-day array for Flutter
    results = []
    for i in range(7):
        current_date = today - datetime.timedelta(days=6-i)
        date_str = str(current_date)
        
        day_meals = meal_dict.get(date_str, {"consumed": 0, "protein": 0, "carbs": 0, "fats": 0})
        day_burned = fitbit_dict.get(date_str, 0)

        results.append({
            "date": date_str,
            "day_name": current_date.strftime("%a"), # "Mon", "Tue", etc.
            "consumed": day_meals["consumed"],
            "burned": day_burned,
            "protein": day_meals["protein"],
            "carbs": day_meals["carbs"],
            "fats": day_meals["fats"]
        })
        
    return results