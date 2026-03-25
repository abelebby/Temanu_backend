from pydantic import BaseModel, EmailStr
from datetime import date
from datetime import datetime
from typing import List, Optional


class UserCreate(BaseModel):
    email: EmailStr
    name: str
    preferred_name: str
    username: str
    password: str
    gender: str
    dob: str
    blood_type: str
    otp_code: str

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
class UserUpdate(BaseModel):
    name: Optional[str] = None
    preferred_name: Optional[str] = None
    gender: Optional[str] = None
    dob: Optional[str] = None
    blood_type: Optional[str] = None

class VerifyRegistrationOTP(BaseModel):
    email: EmailStr
    code: str

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

# ===== Health Metrics Schemas =====
class HealthMetricCreate(BaseModel):
    blood_glucose: Optional[float] = None
    heart_rate: Optional[int] = None
    oxygen_saturation: Optional[float] = None
    blood_pressure_systolic: Optional[int] = None
    blood_pressure_diastolic: Optional[int] = None
    calories: Optional[int] = None
    body_weight: Optional[float] = None

class HealthMetricOut(BaseModel):
    id: int
    user_id: int
    blood_glucose: Optional[float]
    heart_rate: Optional[int]
    oxygen_saturation: Optional[float]
    blood_pressure_systolic: Optional[int]
    blood_pressure_diastolic: Optional[int]
    calories: Optional[int]
    body_weight: Optional[float]
    timestamp: datetime

    class Config:
        from_attributes = True


#password resets~


class RequestOTP(BaseModel):
    email: EmailStr
    username: str
    password: str

class VerifyOTP(BaseModel):
    email: str
    code: str
    new_password: str


class RequestChangePasswordOTP(BaseModel):
    pass  # no fields needed we get email from token

class VerifyChangePassword(BaseModel):
    code: str
    new_password: str

class FitbitTokenSave(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None

# ===== Meal Log Schemas =====
class MealCreate(BaseModel):
    name: str
    calories: int
    protein: Optional[float] = 0.0
    carbs: Optional[float] = 0.0
    fats: Optional[float] = 0.0

class MealOut(BaseModel):
    id: int
    user_id: int
    name: str
    calories: int
    protein: float
    carbs: float
    fats: float
    timestamp: datetime

    class Config:
        from_attributes = True

# ===== Medication Schemas =====
class MedicationCreate(BaseModel):
    name: str
    dosage: str
    inventory: float
    unit: str
    times: list[str]

class MedicationOut(BaseModel):
    id: int
    name: str
    dosage: str
    inventory: float
    unit: str
    times: list[str]
    doses_taken_today: int
    adherence_score: int = 100

class Config:
    from_attributes = True

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str

class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []

# --- DOCTOR SCHEMAS ---
class DoctorOut(BaseModel):
    id: str
    name: str
    specialisation: Optional[str] = None
    qualifications: Optional[str] = None  # Maps to 'education' in DB
    clinic_name: Optional[str] = None
    messaging_platform: Optional[str] = None
    platform_link: Optional[str] = None
    profile_image_url: Optional[str] = None

    class Config:
        from_attributes = True

# --- APPOINTMENT SCHEMAS ---
class AppointmentCreate(BaseModel):
    doctor_id: str
    appointment_time: datetime
    purpose: str

class AppointmentOut(BaseModel):
    id: int
    doctor_id: str
    appointment_time: datetime
    purpose: str
    status: str
    doctor: DoctorOut # Includes the doctor's info in the response!

    class Config:
        from_attributes = True

# --- MEDICAL RECORD SCHEMAS ---
class MedicalRecordCreate(BaseModel):
    doctor_id: str
    file_name: str
    record_type: str
    file_url: str
    description: Optional[str] = None

class MedicalRecordOut(BaseModel):
    id: int
    doctor_id: str
    file_name: str
    record_type: str
    file_url: str
    created_at: datetime

    class Config:
        from_attributes = True

class LinkDoctorRequest(BaseModel):
    doctor_id: str
# ===== DOCTOR PORTAL SCHEMAS =====

class DoctorLogin(BaseModel):
    username: str
    password: str

class DoctorProfileOut(BaseModel):
    id: str
    email: str
    name: str
    preferred_name: Optional[str] = None
    username: Optional[str] = None
    gender: Optional[str] = None
    dob: Optional[str] = None
    education: Optional[str] = None
    specialisation: Optional[str] = None
    clinic_name: Optional[str] = None
    clinic_address: Optional[str] = None
    messaging_platform: Optional[str] = None
    platform_link: Optional[str] = None
    profile_image_url: Optional[str] = None

    class Config:
        from_attributes = True

class DoctorProfileUpdate(BaseModel):
    preferred_name: Optional[str] = None
    gender: Optional[str] = None
    dob: Optional[str] = None
    education: Optional[str] = None
    specialisation: Optional[str] = None
    clinic_name: Optional[str] = None
    clinic_address: Optional[str] = None
    messaging_platform: Optional[str] = None
    platform_link: Optional[str] = None
    profile_image_url: Optional[str] = None

class DoctorPatientOut(BaseModel):
    id: int
    name: str
    preferred_name: str
    username: str
    gender: Optional[str] = None
    dob: Optional[str] = None
    blood_type: Optional[str] = None

    class Config:
        from_attributes = True

class DoctorAppointmentOut(BaseModel):
    id: int
    user_id: int
    patient_name: str
    patient_preferred_name: str
    appointment_time: datetime
    purpose: Optional[str] = None
    status: str

class DoctorRecordOut(BaseModel):
    id: int
    user_id: int
    patient_name: str
    file_name: str
    record_type: Optional[str] = None
    file_url: str
    description: Optional[str] = None
    created_at: datetime

class AppointmentStatusUpdate(BaseModel):
    status: str  # "Completed" or "Cancelled"


    