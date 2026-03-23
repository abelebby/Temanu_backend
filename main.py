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
from datetime import date, timedelta, datetime
from fastapi.middleware.cors import CORSMiddleware
import requests
from fastapi import Header
from apscheduler.schedulers.background import BackgroundScheduler
import smtplib
from email.message import EmailMessage
import re 

# Assuming your database session generator is called SessionLocal
from app.database import SessionLocal

load_dotenv()

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

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

@app.on_event("startup")
def start_scheduler():
    scheduler = BackgroundScheduler()
    # Runs the check_medications function every 60 seconds
    scheduler.add_job(check_medications_and_notify, 'interval', minutes=1)
    scheduler.start()
    print("Background Medication Scheduler Started!")

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

# ==========================================
# NEW: Global Password Validator
# ==========================================
def validate_strong_password(password: str) -> str | None:
    if len(password) < 8:
        return "Must be at least 8 characters long"
    if not re.search(r"[A-Z]", password):
        return "Must contain at least one uppercase letter"
    if not re.search(r"[a-z]", password):
        return "Must contain at least one lowercase letter"
    if not re.search(r"[0-9]", password):
        return "Must contain at least one number"
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return "Must contain at least one special symbol"
    
    return None # Return None if it passes all checks

# ==========================================

@app.post("/register/request-otp")
async def request_registration_otp(request: schemas.RequestOTP, db: Session = Depends(get_db)):
    # 1. Check if Username is already taken
    if db.query(models.User).filter(models.User.username == request.username).first():
        raise HTTPException(status_code=400, detail="Username is already taken")

    # 2. Check Password Strength
    password_error = validate_strong_password(request.password)
    if password_error:
        raise HTTPException(status_code=400, detail=password_error)

    # 3. Check if Email is already registered
    if db.query(models.User).filter(models.User.email == request.email).first():
        raise HTTPException(status_code=400, detail="Email is already registered")

    # 4. Generate a 6-digit OTP
    code = str(random.randint(100000, 999999))
    expires_at = datetime.utcnow() + timedelta(minutes=15)

    # 5. Clear any existing OTPs for this email
    db.query(models.OTPCode).filter(models.OTPCode.email == request.email).delete()

    # 6. Save the new OTP
    otp = models.OTPCode(email=request.email, code=code, expires_at=expires_at)
    db.add(otp)
    db.commit()

    # 7. Send the email
    message = MessageSchema(
        subject="TemanU Registration Verification",
        recipients=[request.email],
        body=f"Welcome to TemanU!\n\nYour registration verification code is: {code}\n\nThis code expires in 15 minutes.",
        subtype="plain"
    )
    fm = FastMail(mail_config)
    await fm.send_message(message)

    return {"message": "Verification OTP sent to your email"}

@app.post("/register/verify-otp")
def verify_registration_otp(request: schemas.VerifyRegistrationOTP, db: Session = Depends(get_db)):
    otp = db.query(models.OTPCode).filter(
        models.OTPCode.email == request.email,
        models.OTPCode.code == request.code
    ).first()

    if not otp:
        raise HTTPException(status_code=400, detail="Invalid Verification Code")

    if otp.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Verification code has expired.")

    return {"message": "OTP verified successfully"}


@app.post("/register")
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    # 1. --- NEW: Verify the OTP First! ---
    otp = db.query(models.OTPCode).filter(
        models.OTPCode.email == user.email,
        models.OTPCode.code == user.otp_code
    ).first()

    if not otp:
        raise HTTPException(status_code=400, detail="Invalid Verification Code")

    if otp.expires_at < datetime.utcnow():
        db.delete(otp)
        db.commit()
        raise HTTPException(status_code=400, detail="Verification code has expired. Please request a new one.")

    # 2. Check if email or username already exists
    if db.query(models.User).filter(models.User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    if db.query(models.User).filter(models.User.username == user.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")

    # 3. Check Password Strength (from our previous step!)
    password_error = validate_strong_password(user.password)
    if password_error:
        raise HTTPException(status_code=400, detail=password_error)

    # 4. Create the User
    new_user = models.User(
        email=user.email,
        name=user.name,
        preferred_name=user.preferred_name,
        username=user.username,
        password_hash=hash_password(user.password),
        gender=user.gender,
        dob=user.dob,
        blood_type=user.blood_type,
    )

    db.add(new_user)
    
    # 5. Clean up the used OTP
    db.delete(otp)
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

@app.put("/users/me", response_model=schemas.UserOut)
def update_user_profile(
    update_data: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 1. Re-fetch the user so it is securely attached to the CURRENT session
    db_user = db.query(models.User).filter(models.User.id == current_user.id).first()

    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # 2. Apply the updates to the newly fetched object
    if update_data.name: db_user.name = update_data.name
    if update_data.preferred_name: db_user.preferred_name = update_data.preferred_name
    if update_data.gender: db_user.gender = update_data.gender
    if update_data.dob: db_user.dob = update_data.dob
    if update_data.blood_type: db_user.blood_type = update_data.blood_type

    # 3. Commit and refresh safely!
    db.commit()
    db.refresh(db_user)
    
    return db_user
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

@app.get("/fitbit/steps/intraday/{date}")
def get_fitbit_intraday_steps(
    date: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 1. Grab the user's Fitbit token
    fitbit_data = db.query(models.FitbitToken).filter(models.FitbitToken.user_id == current_user.id).first()
    if not fitbit_data or not fitbit_data.access_token:
        raise HTTPException(status_code=400, detail="Fitbit account not linked")

    # 2. THE FIX: Ask Fitbit for 15-minute intervals instead of 1hr
    url = f"https://api.fitbit.com/1/user/-/activities/steps/date/{date}/1d/15min.json"
    headers = {"Authorization": f"Bearer {fitbit_data.access_token}"}
    response = requests.get(url, headers=headers)

    if response.status_code == 401:
        db.delete(fitbit_data)
        db.commit()
        raise HTTPException(status_code=401, detail="Fitbit token expired. Please reconnect.")
        
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Fitbit API error")

    data = response.json()

    # 3. Aggregate the 15-minute chunks into 24 hourly chunks for Flutter!
    if "activities-steps-intraday" in data and "dataset" in data["activities-steps-intraday"]:
        raw_dataset = data["activities-steps-intraday"]["dataset"]
        
        # Create a dictionary holding 24 hours, starting at 0 steps
        hourly_data = {f"{i:02d}:00:00": 0 for i in range(24)}
        
        # Loop through the 15-minute increments and sum them up by hour
        for item in raw_dataset:
            hour_key = item["time"][:2] + ":00:00" # Grabs the "14" from "14:15:00"
            hourly_data[hour_key] += int(item["value"])
            
        # Reformat it back into the array structure Flutter expects
        aggregated_dataset = [{"time": k, "value": v} for k, v in hourly_data.items()]
        data["activities-steps-intraday"]["dataset"] = aggregated_dataset

    return data

@app.get("/fitbit/steps/timeseries/{period}/{date}")
def get_fitbit_timeseries_steps(
    period: str,
    date: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 1. Grab the user's Fitbit token
    fitbit_data = db.query(models.FitbitToken).filter(models.FitbitToken.user_id == current_user.id).first()
    if not fitbit_data or not fitbit_data.access_token:
        raise HTTPException(status_code=400, detail="Fitbit account not linked")

    # 2. Hit the TIME SERIES endpoint
    url = f"https://api.fitbit.com/1/user/-/activities/steps/date/{date}/{period}.json"
    headers = {"Authorization": f"Bearer {fitbit_data.access_token}"}
    response = requests.get(url, headers=headers)

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

    if otp.expires_at < datetime.utcnow():
        db.delete(otp)
        db.commit()
        raise HTTPException(status_code=400, detail="OTP has expired")

    user = db.query(models.User).filter(models.User.email == request.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    password_error = validate_strong_password(request.new_password)
    if password_error:
        raise HTTPException(status_code=400, detail=password_error)

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
    expires_at = datetime.utcnow() + timedelta(minutes=15)

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

    if otp.expires_at < datetime.utcnow():
        db.delete(otp)
        db.commit()
        raise HTTPException(status_code=400, detail="OTP has expired")

    password_error = validate_strong_password(request.new_password)
    if password_error:
        raise HTTPException(status_code=400, detail=password_error)

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
    today = date.today()
    
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
    today = date.today()
    seven_days_ago = today - timedelta(days=6) # Get the last 7 days inclusive

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
        current_date = today - timedelta(days=6-i)
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

@app.post("/medications", response_model=schemas.MedicationOut)
def add_medication(
    med: schemas.MedicationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Convert the list of times into a single string for the database
    times_str = ",".join(med.times) if med.times else ""

    new_med = models.Medication(
        user_id=current_user.id,
        name=med.name,
        dosage=med.dosage,
        inventory=med.inventory,
        unit=med.unit,
        times=times_str
    )
    db.add(new_med)
    db.commit()
    db.refresh(new_med)
    
    return schemas.MedicationOut(
        id=new_med.id, name=new_med.name, dosage=new_med.dosage, 
        inventory=new_med.inventory, unit=new_med.unit, 
        times=med.times, doses_taken_today=0
    )

@app.get("/medications", response_model=list[schemas.MedicationOut])
def get_medications(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    today = date.today()
    meds = db.query(models.Medication).filter(models.Medication.user_id == current_user.id).all()
    
    results = []
    for med in meds:
        # 1. Calculate today's taken doses
        doses_taken = db.query(models.MedicationLog).filter(
            models.MedicationLog.medication_id == med.id,
            func.date(models.MedicationLog.taken_at) == today
        ).count()
        
        times_list = med.times.split(",") if med.times else []
        doses_per_day = len(times_list) if times_list else 1
        
        # --- THE INDIVIDUAL ADHERENCE MATH ---
        # 2. Figure out how many days it has been active (Max 6 past days + today = 7 day window)
        created_date = med.created_at.date() if med.created_at else today
        delta_days = (today - created_date).days
        past_days = min(6, max(0, delta_days)) 
            
        expected_past_doses = past_days * doses_per_day
        
        # Today's doses are only added to the expected total if they were ACTUALLY taken
        expected_total = expected_past_doses + doses_taken
        
        # 3. Get the actual taken doses from the past days
        if past_days > 0:
            start_date = today - timedelta(days=past_days)
            taken_past = db.query(models.MedicationLog).filter(
                models.MedicationLog.medication_id == med.id,
                func.date(models.MedicationLog.taken_at) >= start_date,
                func.date(models.MedicationLog.taken_at) < today
            ).count()
        else:
            taken_past = 0
            
        taken_total = taken_past + doses_taken
        
        # 4. Calculate final percentage
        if expected_total == 0:
            adherence_score = 100
        else:
            # round() handles things like 66.6 -> 67%
            adherence_score = int(round((taken_total / expected_total) * 100))
        # -------------------------------------
        
        results.append(schemas.MedicationOut(
            id=med.id, name=med.name, dosage=med.dosage,
            inventory=med.inventory, unit=med.unit,
            times=times_list, doses_taken_today=doses_taken,
            adherence_score=adherence_score  # Push the new score to Flutter!
        ))
        
    return results

@app.post("/medications/{med_id}/take")
def take_medication(
    med_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 1. Find the pill
    med = db.query(models.Medication).filter(
        models.Medication.id == med_id, 
        models.Medication.user_id == current_user.id
    ).first()
    
    if not med:
        raise HTTPException(status_code=404, detail="Medication not found")

    # 2. Create the log stamp
    new_log = models.MedicationLog(medication_id=med.id, user_id=current_user.id)
    db.add(new_log)
    
    # 3. Safely figure out how much to subtract
    try:
        # Convert the string dosage (e.g. "2" or "1.5") into a float
        dose_amount = float(med.dosage)
    except ValueError:
        # Fallback just in case there's old data with letters in it
        dose_amount = 1.0 

    # 4. Decrease the inventory by the EXACT dosage amount!
    if med.inventory > 0:
        med.inventory -= dose_amount
        # Prevent it from going into negative numbers if they take the last partial dose
        if med.inventory < 0:
            med.inventory = 0 
        
    db.commit()
    return {"message": "Medication logged successfully", "new_inventory": med.inventory}

@app.delete("/medications/{med_id}")
def delete_medication(
    med_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    med = db.query(models.Medication).filter(
        models.Medication.id == med_id, 
        models.Medication.user_id == current_user.id
    ).first()
    
    if not med:
        raise HTTPException(status_code=404, detail="Medication not found")
        
    db.delete(med)
    db.commit()
    return {"message": "Medication deleted successfully"}

@app.get("/medications/adherence")
def get_medication_adherence(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    today = date.today()
    seven_days_ago = today - timedelta(days=6)

    # 1. Get all active medications
    meds = db.query(models.Medication).filter(models.Medication.user_id == current_user.id).all()
    
    if not meds:
        return {"adherence_percentage": 0}
        
    # 2. Calculate how many doses they SHOULD have taken in 7 days
    total_expected_doses = 0
    for med in meds:
        times_list = med.times.split(",") if med.times else ["Anytime"]
        total_expected_doses += len(times_list) * 7

    # 3. Count how many they ACTUALLY took in the last 7 days
    taken_logs_count = db.query(models.MedicationLog).join(models.Medication).filter(
        models.Medication.user_id == current_user.id,
        func.date(models.MedicationLog.taken_at) >= seven_days_ago,
        func.date(models.MedicationLog.taken_at) <= today
    ).count()

    if total_expected_doses == 0:
        return {"adherence_percentage": 0}

    # 4. Calculate the percentage (cap at 100% just in case of over-logging)
    adherence = (taken_logs_count / total_expected_doses) * 100
    return {"adherence_percentage": min(int(adherence), 100)}

@app.put("/medications/{med_id}", response_model=schemas.MedicationOut)
def edit_medication(
    med_id: int,
    med: schemas.MedicationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 1. Find the existing medication
    db_med = db.query(models.Medication).filter(
        models.Medication.id == med_id, 
        models.Medication.user_id == current_user.id
    ).first()
    
    if not db_med:
        raise HTTPException(status_code=404, detail="Medication not found")
        
    # 2. Update all the fields
    times_str = ",".join(med.times) if med.times else ""
    db_med.name = med.name
    db_med.dosage = med.dosage
    db_med.inventory = med.inventory
    db_med.unit = med.unit
    db_med.times = times_str
    
    db.commit()
    db.refresh(db_med)
    
    # 3. Calculate how many doses were taken today so Flutter doesn't break
    today = date.today()
    doses_taken = db.query(models.MedicationLog).filter(
        models.MedicationLog.medication_id == db_med.id,
        func.date(models.MedicationLog.taken_at) == today
    ).count()
    
    times_list = db_med.times.split(",") if db_med.times else []
    
    return schemas.MedicationOut(
        id=db_med.id, name=db_med.name, dosage=db_med.dosage,
        inventory=db_med.inventory, unit=db_med.unit,
        times=times_list, doses_taken_today=doses_taken
    )

# ==========================================
# MEDICATION EMAIL SCHEDULER
# ==========================================

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465 
SENDER_EMAIL = os.getenv("MAIL_EMAIL")
SENDER_PASSWORD = os.getenv("MAIL_PASSWORD")

def send_medication_email(to_email, user_name, med_name, dosage, unit):
    msg = EmailMessage()
    msg.set_content(
        f"Hi {user_name},\n\n"
        f"It is time to take your medication: {dosage} {unit} of {med_name}.\n\n"
        f"Don't forget to log it in your Temanu dashboard once taken!\n\n"
        f"Stay healthy,\nThe Temanu Team"
    )
    msg['Subject'] = f"💊 Reminder: Time to take your {med_name}"
    msg['From'] = SENDER_EMAIL
    msg['To'] = to_email

    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
            print(f"Email sent successfully to {to_email} for {med_name}")
    except Exception as e:
        print(f"Failed to send email: {e}")

def check_medications_and_notify():
    # 1. Get current time in the exact format saved in the DB (e.g., "08:00 AM")
    current_time_str = datetime.now().strftime("%I:%M %p")
    
    # 2. Open a fresh DB session (required because this runs in a background thread)
    db = SessionLocal()
    try:
        # 3. Query all medications
        meds = db.query(models.Medication).all()
        for med in meds:
            # 4. If the exact current minute is in their schedule string
            if med.times and current_time_str in med.times:
                # Find the user to get their email address
                user = db.query(models.User).filter(models.User.id == med.user_id).first()
                if user and user.email:
                    # Optional: Add logic here to check 'MedicationLog' to see if 
                    # they ALREADY took it today before spamming them!
                    
                    send_medication_email(
                        to_email=user.email,
                        user_name=user.preferred_name or "there",
                        med_name=med.name,
                        dosage=med.dosage,
                        unit=med.unit
                    )
    finally:
        db.close() # Always close background DB sessions safely

# ==========================================