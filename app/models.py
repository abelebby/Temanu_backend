from sqlalchemy import JSON, Column, Integer, String, TIMESTAMP,ForeignKey, Date, DateTime, Float
import datetime
from sqlalchemy.sql import func
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(100), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    preferred_name = Column(String(50), nullable=False)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    # --- NEW COLUMNS ---
    gender = Column(String(20), nullable=True)
    dob = Column(String(50), nullable=True) 
    blood_type = Column(String(10), nullable=True)
    # -------------------
    created_at = Column(TIMESTAMP, server_default=func.now())

class Activity(Base):
    __tablename__ = "activity_metrics"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    steps = Column(Integer, nullable=False)
    date = Column(Date, nullable=False)

class OTPCode(Base):
    __tablename__ = "otp_codes"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(100), nullable=False)
    code = Column(String(6), nullable=False)
    expires_at = Column(DateTime, nullable=False)

class HealthMetric(Base):
    __tablename__ = "health_metrics"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Specific metric columns with proper datatypes for charting
    blood_glucose = Column(Float, nullable=True)             # e.g., mg/dL
    heart_rate = Column(Integer, nullable=True)              # e.g., bpm
    oxygen_saturation = Column(Float, nullable=True)         # e.g., %
    blood_pressure_systolic = Column(Integer, nullable=True) # e.g., mmHg
    blood_pressure_diastolic = Column(Integer, nullable=True)# e.g., mmHg
    calories = Column(Integer, nullable=True)                # e.g., kcal
    body_weight = Column(Float, nullable=True)               # e.g., kg
    
    timestamp = Column(TIMESTAMP, server_default=func.now())

class FitbitToken(Base):
    __tablename__ = "fitbit_tokens"

    id = Column(Integer, primary_key=True, index=True)
    # The Foreign Key links this token directly to a specific user
    # unique=True ensures one user can't accidentally save 5 different Fitbit accounts
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    access_token = Column(String(1000), nullable=False)
    refresh_token = Column(String(1000), nullable=True)

class MealLog(Base):
    __tablename__ = "meal_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    name = Column(String(100), nullable=False)
    calories = Column(Integer, nullable=False)
    protein = Column(Float, default=0.0)
    carbs = Column(Float, default=0.0)
    fats = Column(Float, default=0.0)
    
    timestamp = Column(TIMESTAMP, server_default=func.now())

class Medication(Base):
    __tablename__ = "medications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    name = Column(String(100), nullable=False)
    dosage = Column(String(50), nullable=True) 
    inventory = Column(Float, default=0.0)    
    
    unit = Column(String(50), default="pills") # e.g., ml, puffs, drops
    times = Column(String(255), nullable=True) # e.g., "08:00 AM,08:00 PM"
    
    created_at = Column(TIMESTAMP, server_default=func.now())

class MedicationLog(Base):
    __tablename__ = "medication_logs"

    id = Column(Integer, primary_key=True, index=True)
    medication_id = Column(Integer, ForeignKey("medications.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    taken_at = Column(TIMESTAMP, server_default=func.now())

class FitbitCache(Base):
    __tablename__ = "fitbit_cache"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    date = Column(String, index=True) # Stored as "YYYY-MM-DD"
    endpoint = Column(String, index=True) # Identifies if it's "activity", "intraday", etc.
    data = Column(JSON) # Stores the exact payload Fitbit gave us
    updated_at = Column(DateTime, default=datetime.utcnow)