from sqlalchemy import Column, Integer, String, TIMESTAMP,ForeignKey, Date, DateTime
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
    metric_type = Column(String(50), nullable=False)
    value = Column(String(50), nullable=False)
    unit = Column(String(20), nullable=False)
    timestamp = Column(TIMESTAMP, server_default=func.now())
