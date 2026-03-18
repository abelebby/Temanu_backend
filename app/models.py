from sqlalchemy import Column, Integer, String, TIMESTAMP,ForeignKey, Date, DateTime, Float
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
