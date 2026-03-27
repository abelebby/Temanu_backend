from sqlalchemy import JSON, Column, Integer, String, TIMESTAMP, ForeignKey, Date, DateTime, Float, Text, Boolean
from datetime import datetime, timezone
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(100), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    preferred_name = Column(String(50), nullable=False)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    
    gender = Column(String(20), nullable=True)
    dob = Column(String(50), nullable=True) 
    blood_type = Column(String(10), nullable=True)
    
    created_at = Column(TIMESTAMP, server_default=func.now())

    appointments = relationship("Appointment", back_populates="user", cascade="all, delete-orphan")
    medical_records = relationship("MedicalRecord", back_populates="user", cascade="all, delete-orphan")
    personal_doctors = relationship("PersonalDoctor", back_populates="user", cascade="all, delete-orphan")


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
    
    blood_glucose = Column(Float, nullable=True)             
    heart_rate = Column(Integer, nullable=True)              
    oxygen_saturation = Column(Float, nullable=True)         
    blood_pressure_systolic = Column(Integer, nullable=True) 
    blood_pressure_diastolic = Column(Integer, nullable=True)
    calories = Column(Integer, nullable=True)                
    body_weight = Column(Float, nullable=True)               
    
    timestamp = Column(TIMESTAMP, server_default=func.now())

class FitbitToken(Base):
    __tablename__ = "fitbit_tokens"

    id = Column(Integer, primary_key=True, index=True)
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
    
    unit = Column(String(50), default="pills") 
    times = Column(String(255), nullable=True) 
    
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

    date = Column(String(50), index=True) 
    endpoint = Column(String(100), index=True) 
    
    data = Column(JSON) 
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

# ==========================================
# DOCTORS TABLE
# ==========================================
class Doctor(Base):
    __tablename__ = "doctors"

    # --- THE FIX: Added lengths to all String columns for MySQL ---
    id = Column(String(50), primary_key=True, index=True) 
    email = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    
    name = Column(String(100), nullable=False)
    preferred_name = Column(String(50))
    username = Column(String(50), unique=True, index=True)
    gender = Column(String(20))
    dob = Column(String(50)) 
    
    education = Column(String(255))
    specialisation = Column(String(100))
    clinic_name = Column(String(150))
    clinic_address = Column(Text) # Text doesn't need a length
    
    messaging_platform = Column(String(50)) 
    platform_link = Column(String(255))
    profile_image_url = Column(String(500))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    appointments = relationship("Appointment", back_populates="doctor", cascade="all, delete-orphan")
    medical_records = relationship("MedicalRecord", back_populates="doctor", cascade="all, delete-orphan")
    patients = relationship("PersonalDoctor", back_populates="doctor", cascade="all, delete-orphan")


# ==========================================
# APPOINTMENTS TABLE
# ==========================================
class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(String(50), ForeignKey("doctors.id"), nullable=False) # Must match Doctor ID length
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False) 
    
    appointment_time = Column(DateTime(timezone=True), nullable=False)
    purpose = Column(Text)
    status = Column(String(50), default="Upcoming") 
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    doctor = relationship("Doctor", back_populates="appointments")
    user = relationship("User", back_populates="appointments") 


# ==========================================
# MEDICAL RECORDS TABLE
# ==========================================
class MedicalRecord(Base):
    __tablename__ = "medical_records"

    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(String(50), ForeignKey("doctors.id"), nullable=False) # Must match Doctor ID length
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    file_name = Column(String(255), nullable=False)
    record_type = Column(String(100)) 
    file_url = Column(String(1000), nullable=False) 
    description = Column(Text)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    doctor = relationship("Doctor", back_populates="medical_records")
    user = relationship("User", back_populates="medical_records")


# ==========================================
# PERSONAL DOCTORS (JUNCTION TABLE)
# ==========================================
class PersonalDoctor(Base):
    __tablename__ = "personal_doctors"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    doctor_id = Column(String(50), ForeignKey("doctors.id"), primary_key=True) 
    
    # --- NEW: Permission Variables ---
    can_view_heart_rate = Column(Boolean, default=True)
    can_view_blood_pressure = Column(Boolean, default=True)
    can_view_blood_glucose = Column(Boolean, default=True)
    can_view_oxygen_saturation = Column(Boolean, default=True)
    can_view_body_weight = Column(Boolean, default=True)
    can_view_medications = Column(Boolean, default=True)
    can_view_activity = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    doctor = relationship("Doctor", back_populates="patients")
    user = relationship("User", back_populates="personal_doctors")