import boto3
from pydantic import BaseModel
from botocore.client import Config
import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import date, timedelta
from app.database import get_db
from app import models, schemas
from app.auth import verify_password, create_doctor_access_token, get_current_doctor

# Initialize S3 Client
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION"),
    endpoint_url=f"https://s3.{os.getenv('AWS_REGION')}.amazonaws.com", 
    config=Config(signature_version='s3v4') 
)
BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

# ==========================================
# DOCTOR PORTAL ROUTER
# ==========================================
# Two prefixes: /doctors for auth/profile, /care-team/doctor for patient data
# We use two separate routers for clean URL separation

doctor_auth_router = APIRouter(
    prefix="/doctors",
    tags=["Doctor Portal — Auth & Profile"]
)

doctor_data_router = APIRouter(
    prefix="/care-team/doctor",
    tags=["Doctor Portal — Patient Data"]
)


# ==========================================
# 1. DOCTOR LOGIN
# ==========================================
@doctor_auth_router.post("/login")
def doctor_login(credentials: schemas.DoctorLogin, db: Session = Depends(get_db)):
    """Authenticates a doctor by username/password and returns a JWT."""
    doctor = db.query(models.Doctor).filter(
        models.Doctor.username == credentials.username
    ).first()

    if not doctor or not verify_password(credentials.password, doctor.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Use "doc_" prefix so get_current_doctor can identify it
    token = create_doctor_access_token(data={"sub": f"doc_{doctor.id}"})

    return {
        "access_token": token,
        "token_type": "bearer",
        "doctor_id": doctor.id,
        "doctor_name": doctor.name,
        "preferred_name": doctor.preferred_name or doctor.name,
    }


# ==========================================
# 2. GET OWN PROFILE
# ==========================================
@doctor_auth_router.get("/me", response_model=schemas.DoctorProfileOut)
def get_doctor_profile(current_doctor: models.Doctor = Depends(get_current_doctor)):
    """Returns the authenticated doctor's full profile."""
    return current_doctor


# ==========================================
# 3. UPDATE OWN PROFILE
# ==========================================
@doctor_auth_router.put("/me", response_model=schemas.DoctorProfileOut)
def update_doctor_profile(
    update_data: schemas.DoctorProfileUpdate,
    db: Session = Depends(get_db),
    current_doctor: models.Doctor = Depends(get_current_doctor)
):
    """Updates the authenticated doctor's profile fields."""
    db_doctor = db.query(models.Doctor).filter(models.Doctor.id == current_doctor.id).first()
    if not db_doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    # Apply only the fields that were provided
    update_fields = update_data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        if value is not None:
            setattr(db_doctor, field, value)

    db.commit()
    db.refresh(db_doctor)
    return db_doctor


# ==========================================
# 4. GET ALL LINKED PATIENTS
# ==========================================
@doctor_data_router.get("/patients", response_model=List[schemas.DoctorPatientOut])
def get_doctor_patients(
    db: Session = Depends(get_db),
    current_doctor: models.Doctor = Depends(get_current_doctor)
):
    """Returns all patients who have added this doctor to their care team."""
    patients = db.query(models.User).join(
        models.PersonalDoctor, models.User.id == models.PersonalDoctor.user_id
    ).filter(
        models.PersonalDoctor.doctor_id == current_doctor.id
    ).all()

    return patients


# ==========================================
# 5. GET PATIENT'S HEALTH METRICS
# ==========================================
@doctor_data_router.get("/patients/{user_id}/metrics")
def get_patient_metrics(
    user_id: int,
    db: Session = Depends(get_db),
    current_doctor: models.Doctor = Depends(get_current_doctor)
):
    """Returns the latest health metrics for a specific patient."""
    # Verify this patient is linked to this doctor
    link = db.query(models.PersonalDoctor).filter(
        models.PersonalDoctor.doctor_id == current_doctor.id,
        models.PersonalDoctor.user_id == user_id
    ).first()
    
    if not link:
        raise HTTPException(status_code=403, detail="This patient is not in your care team")

    # Get the latest 30 health records for charting
    metrics = db.query(models.HealthMetric).filter(
        models.HealthMetric.user_id == user_id
    ).order_by(models.HealthMetric.timestamp.desc()).limit(30).all()

    # Format into a clean response
    result = []
    for m in metrics:
        entry = {"timestamp": m.timestamp.isoformat() + "Z" if m.timestamp else None}
        
        # 🔒 SECURITY CHECK: Only attach the metric if the patient granted permission!
        if link.can_view_heart_rate and m.heart_rate is not None:
            entry["heart_rate"] = m.heart_rate
            
        if link.can_view_blood_pressure:
            if m.blood_pressure_systolic is not None:
                entry["blood_pressure_systolic"] = m.blood_pressure_systolic
            if m.blood_pressure_diastolic is not None:
                entry["blood_pressure_diastolic"] = m.blood_pressure_diastolic
                
        if link.can_view_blood_glucose and m.blood_glucose is not None:
            entry["blood_glucose"] = m.blood_glucose
            
        if link.can_view_oxygen_saturation and m.oxygen_saturation is not None:
            entry["oxygen_saturation"] = m.oxygen_saturation
            
        if link.can_view_body_weight and m.body_weight is not None:
            entry["body_weight"] = m.body_weight
            
        # Only append the entry if it contains more than just the timestamp
        if len(entry) > 1:
            result.append(entry)

    return result


# ==========================================
# 6. GET PATIENT'S MEDICATIONS
# ==========================================
@doctor_data_router.get("/patients/{user_id}/medications")
def get_patient_medications(
    user_id: int,
    db: Session = Depends(get_db),
    current_doctor: models.Doctor = Depends(get_current_doctor)
):
    """Returns the medication list for a specific patient (read-only for doctor)."""
    # Verify link
    link = db.query(models.PersonalDoctor).filter(
        models.PersonalDoctor.doctor_id == current_doctor.id,
        models.PersonalDoctor.user_id == user_id
    ).first()
    
    if not link:
        raise HTTPException(status_code=403, detail="This patient is not in your care team")

    # 🔒 SECURITY CHECK: Does the doctor have permission to view medications?
    if not link.can_view_medications:
        return [] # Return an empty list so the doctor just sees "No medications recorded"

    today = date.today()
    meds = db.query(models.Medication).filter(
        models.Medication.user_id == user_id
    ).all()

    results = []
    for med in meds:
        doses_taken = db.query(models.MedicationLog).filter(
            models.MedicationLog.medication_id == med.id,
            func.date(models.MedicationLog.taken_at) == today
        ).count()

        times_list = med.times.split(",") if med.times else []

        results.append({
            "id": med.id,
            "name": med.name,
            "dosage": med.dosage,
            "inventory": med.inventory,
            "unit": med.unit,
            "times": times_list,
            "doses_taken_today": doses_taken,
        })

    return results

# ==========================================
# 6.5 GET PATIENT'S ACTIVITY / STEPS
# ==========================================
@doctor_data_router.get("/patients/{user_id}/activity")
def get_patient_activity(
    user_id: int,
    db: Session = Depends(get_db),
    current_doctor: models.Doctor = Depends(get_current_doctor)
):
    # 1. Verify link & permissions
    link = db.query(models.PersonalDoctor).filter(
        models.PersonalDoctor.doctor_id == current_doctor.id,
        models.PersonalDoctor.user_id == user_id
    ).first()
    
    if not link or not link.can_view_activity:
        return [] 

    # 2. Fetch the most recent cache payloads for this user
    # We grab the last few requests the patient app made to Fitbit
    cached_rows = db.query(models.FitbitCache).filter(
        models.FitbitCache.user_id == user_id
    ).order_by(models.FitbitCache.updated_at.desc()).limit(10).all()

    # We use a dictionary to automatically prevent duplicate dates.
    # Because we ordered by `updated_at.desc()`, the first time we see a date, it is the freshest!
    step_dict = {}

    for row in cached_rows:
        if row.data:
            # Check if this row contains a time-series array (e.g., from the "1w" or "1m" fetch)
            if "activities-steps" in row.data:
                for item in row.data["activities-steps"]:
                    date_str = item.get("dateTime")
                    
                    # Fitbit returns the value as a string (e.g., "5441"), so we convert it to an integer
                    try:
                        val = int(float(item.get("value", 0)))
                    except ValueError:
                        val = 0
                        
                    if date_str and date_str not in step_dict:
                        step_dict[date_str] = val
                        
            # Fallback: In case the cache is just a single day's summary
            elif "summary" in row.data and "steps" in row.data["summary"]:
                if row.date and row.date not in step_dict:
                    step_dict[row.date] = row.data["summary"]["steps"]

    # 3. Sort the dates chronologically to find the most recent 14 days
    sorted_dates = sorted(step_dict.keys(), reverse=True)
    top_14_dates = sorted_dates[:14]

    # 4. Format them for Flutter
    results = []
    for d in top_14_dates:
        results.append({
            "date": d,
            "steps": step_dict[d]
        })

    return results

# ==========================================
# 7. GET ALL DOCTOR'S APPOINTMENTS
# ==========================================
@doctor_data_router.get("/appointments", response_model=List[schemas.DoctorAppointmentOut])
def get_doctor_appointments(
    db: Session = Depends(get_db),
    current_doctor: models.Doctor = Depends(get_current_doctor)
):
    """Returns all appointments for this doctor, with patient info."""
    appointments = db.query(models.Appointment).filter(
        models.Appointment.doctor_id == current_doctor.id
    ).order_by(models.Appointment.appointment_time.desc()).all()

    results = []
    for appt in appointments:
        user = db.query(models.User).filter(models.User.id == appt.user_id).first()
        results.append(schemas.DoctorAppointmentOut(
            id=appt.id,
            user_id=appt.user_id,
            patient_name=user.name if user else "Unknown",
            patient_preferred_name=user.preferred_name if user else "Unknown",
            appointment_time=appt.appointment_time,
            purpose=appt.purpose,
            status=appt.status,
        ))

    return results


# ==========================================
# 8. UPDATE APPOINTMENT STATUS
# ==========================================
@doctor_data_router.patch("/appointments/{appointment_id}/status")
def update_appointment_status(
    appointment_id: int,
    update: schemas.AppointmentStatusUpdate,
    db: Session = Depends(get_db),
    current_doctor: models.Doctor = Depends(get_current_doctor)
):
    """Updates an appointment's status (Completed or Cancelled)."""
    if update.status not in ("Completed", "Cancelled"):
        raise HTTPException(status_code=400, detail="Status must be 'Completed' or 'Cancelled'")

    appt = db.query(models.Appointment).filter(
        models.Appointment.id == appointment_id,
        models.Appointment.doctor_id == current_doctor.id
    ).first()

    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if appt.status != "Upcoming":
        raise HTTPException(status_code=400, detail=f"Cannot change status of a '{appt.status}' appointment")

    appt.status = update.status
    db.commit()

    return {"message": f"Appointment marked as {update.status}"}

# ==========================================
# 9. CREATE APPOINTMENT 
# ==========================================
@doctor_data_router.post("/appointments")
def create_patient_appointment(
    appt: schemas.DoctorPortalAppointmentCreate, # We will define this below!
    db: Session = Depends(get_db),
    current_doctor: models.Doctor = Depends(get_current_doctor) # Your doctor auth dependency
):
    """Allows a doctor to schedule a new appointment with a linked patient."""
    
    # Optional: Verify the patient actually exists
    patient = db.query(models.User).filter(models.User.id == appt.user_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    new_appt = models.Appointment(
        user_id=appt.user_id,             # The patient receiving the appointment
        doctor_id=current_doctor.id,      # The doctor making the appointment
        appointment_time=appt.appointment_time,
        purpose=appt.purpose,
        status="Upcoming"
    )
    
    db.add(new_appt)
    db.commit()
    db.refresh(new_appt)
    
    return new_appt

# ==========================================
# 10. GET MEDICAL RECORDS (filterable by patient)
# ==========================================
@doctor_data_router.get("/records")
def get_doctor_records(
    user_id: Optional[int] = Query(None, description="Filter by patient ID"),
    db: Session = Depends(get_db),
    current_doctor: models.Doctor = Depends(get_current_doctor)
):
    """Returns medical records uploaded by this doctor, optionally filtered by patient."""
    query = db.query(models.MedicalRecord).filter(
        models.MedicalRecord.doctor_id == current_doctor.id
    )

    if user_id is not None:
        query = query.filter(models.MedicalRecord.user_id == user_id)

    records = query.order_by(models.MedicalRecord.created_at.desc()).all()

    results = []
    for rec in records:
        user = db.query(models.User).filter(models.User.id == rec.user_id).first()
        results.append({
            "id": rec.id,
            "user_id": rec.user_id,
            "patient_name": user.name if user else "Unknown",
            "file_name": rec.file_name,
            "record_type": rec.record_type,
            "file_url": rec.file_url,
            "description": rec.description,
            "created_at": rec.created_at.isoformat() if rec.created_at else None,
        })

    return results

# ==========================================
# 10.5 SAVE MEDICAL RECORD (For Doctors)
# ==========================================

# Create a dedicated schema so we don't clash with the patient schemas
class DoctorRecordCreate(BaseModel):
    user_id: int
    file_name: str
    record_type: str
    file_url: str
    description: Optional[str] = None

@doctor_data_router.post("/records")
def save_doctor_medical_record(
    record_data: DoctorRecordCreate,
    db: Session = Depends(get_db),
    current_doctor: models.Doctor = Depends(get_current_doctor)
):
    """Saves the metadata for a document uploaded by a doctor directly to a patient's vault."""
    
    # 1. Security Check: Ensure this patient is actually linked to this doctor!
    link = db.query(models.PersonalDoctor).filter(
        models.PersonalDoctor.doctor_id == current_doctor.id,
        models.PersonalDoctor.user_id == record_data.user_id
    ).first()
    
    if not link:
        raise HTTPException(status_code=403, detail="Patient is not in your care team")
        
    # 2. Save the record
    new_record = models.MedicalRecord(
        user_id=record_data.user_id,
        doctor_id=current_doctor.id,
        file_name=record_data.file_name,
        record_type=record_data.record_type,
        file_url=record_data.file_url,  # This holds the AWS S3 Key
        description=record_data.description
    )
    
    db.add(new_record)
    db.commit()
    db.refresh(new_record)
    
    return new_record

# ==========================================
# 11. GENERATE UPLOAD URL (For Doctors)
# ==========================================
@doctor_data_router.get("/records/upload-url")
def get_doctor_upload_url(
    patient_id: int, # <-- The doctor must specify WHICH patient this file is for
    file_name: str, 
    file_type: str, 
    db: Session = Depends(get_db), 
    current_doctor: models.Doctor = Depends(get_current_doctor)
):
    """Generates a secure 5-minute URL for the doctor to upload a patient file to S3."""
    
    # 1. Verify the doctor is allowed to access this patient
    link = db.query(models.PersonalDoctor).filter(
        models.PersonalDoctor.doctor_id == current_doctor.id,
        models.PersonalDoctor.user_id == patient_id
    ).first()
    
    if not link:
        raise HTTPException(status_code=403, detail="Patient is not in your care team")

    # 2. Create the unique file path (Save it in the patient's folder!)
    unique_filename = f"patients/{patient_id}/{uuid.uuid4()}_{file_name}"
    
    try:
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': BUCKET_NAME,
                'Key': unique_filename,
                'ContentType': file_type
            },
            ExpiresIn=300 # Valid for 5 minutes
        )
        
        return {
            "upload_url": presigned_url,
            "file_key": unique_filename # Flutter will save this in the database
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Could not generate upload URL")

# ==========================================
# 12. GENERATE VIEW/DOWNLOAD URL (For Doctors)
# ==========================================
@doctor_data_router.get("/records/{record_id}/download-url")
def get_doctor_download_url(
    record_id: int, 
    db: Session = Depends(get_db), 
    current_doctor: models.Doctor = Depends(get_current_doctor)
):
    """Generates a temporary URL for a doctor to view a private file."""
    
    record = db.query(models.MedicalRecord).filter(
        models.MedicalRecord.id == record_id,
        models.MedicalRecord.doctor_id == current_doctor.id # Security check!
    ).first()
    
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    try:
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': BUCKET_NAME,
                'Key': record.file_url 
            },
            ExpiresIn=3600 # Valid for 1 hour
        )
        return {"download_url": presigned_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Could not generate download URL")
    
# ==========================================
# 13. SEARCH PATIENTS (For Adding)
# ==========================================
@doctor_data_router.get("/search-patient")
def search_patients(
    query: str,
    db: Session = Depends(get_db),
    current_doctor: models.Doctor = Depends(get_current_doctor)
):
    """Searches for users by name or username to add to care team."""
    search_term = f"%{query}%"
    
    users = db.query(models.User).filter(
        (models.User.name.ilike(search_term)) |
        (models.User.preferred_name.ilike(search_term)) |
        (models.User.username.ilike(search_term))
    ).limit(20).all()

    results = []
    for u in users:
        # Check if they are already linked so the UI can disable the "Add" button
        is_linked = db.query(models.PersonalDoctor).filter(
            models.PersonalDoctor.doctor_id == current_doctor.id,
            models.PersonalDoctor.user_id == u.id
        ).first() is not None

        results.append({
            "id": u.id,
            "name": u.name,
            "preferred_name": u.preferred_name,
            "username": u.username,
            "gender": u.gender,
            "blood_type": u.blood_type,
            "is_linked": is_linked
        })

    return results

# ==========================================
# 14. SEND CARE TEAM REQUEST (Add Patient)
# ==========================================
@doctor_data_router.post("/add-patient/{user_id}")
def add_patient_request(
    user_id: int,
    db: Session = Depends(get_db),
    current_doctor: models.Doctor = Depends(get_current_doctor)
):
    """Sends a request to the patient. The patient must approve it in their app."""
    # 1. Check if patient exists
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Patient not found")

    # 2. Check if already linked
    existing_link = db.query(models.PersonalDoctor).filter(
        models.PersonalDoctor.doctor_id == current_doctor.id,
        models.PersonalDoctor.user_id == user_id
    ).first()
    if existing_link:
        raise HTTPException(status_code=400, detail="Patient is already in your care team")

    # 3. Check if a request is already pending
    # NOTE: Ensure 'CareTeamRequest' matches your actual class name in models.py
    existing_req = db.query(models.CareTeamRequest).filter(
        models.CareTeamRequest.doctor_id == current_doctor.id,
        models.CareTeamRequest.user_id == user_id,
        models.CareTeamRequest.status == "Pending"
    ).first()
    
    if existing_req:
        raise HTTPException(status_code=400, detail="Request already sent and is awaiting patient approval.")

    # 4. Create the new pending request
    new_request = models.CareTeamRequest(
        doctor_id=current_doctor.id,
        user_id=user_id,
        status="Pending"
    )
    
    db.add(new_request)
    db.commit()
    
    return {"message": "Request sent to patient successfully"}

# ==========================================
# 15. GET DOCTOR'S PENDING REQUESTS
# ==========================================
@doctor_data_router.get("/pending-requests")
def get_doctor_pending_requests(
    db: Session = Depends(get_db),
    current_doctor: models.Doctor = Depends(get_current_doctor)
):
    """Gets all requests sent by this doctor that are still pending patient approval."""
    # NOTE: Ensure 'CareTeamRequest' matches your actual class name in models.py
    requests = db.query(models.CareTeamRequest).filter(
        models.CareTeamRequest.doctor_id == current_doctor.id,
        models.CareTeamRequest.status == "Pending"
    ).all()

    results = []
    for req in requests:
        user = db.query(models.User).filter(models.User.id == req.user_id).first()
        if user:
            results.append({
                "id": req.id,
                "user_id": user.id,
                "patient_name": user.preferred_name or user.name,
                "status": req.status
            })

    return results

# ==========================================
# 16. REMOVE PATIENT FROM CARE TEAM
# ==========================================
@doctor_data_router.delete("/remove-patient/{user_id}")
def remove_patient_from_care_team(
    user_id: int,
    db: Session = Depends(get_db),
    current_doctor: models.Doctor = Depends(get_current_doctor)
):
    """Removes the link between the doctor and patient, revoking all access."""
    link = db.query(models.PersonalDoctor).filter(
        models.PersonalDoctor.doctor_id == current_doctor.id,
        models.PersonalDoctor.user_id == user_id
    ).first()

    if not link:
        raise HTTPException(status_code=404, detail="Patient not found in your care team")

    # Delete the connection
    db.delete(link)
    
    # Optional clean-up: Automatically cancel any "Pending" requests between them just in case
    db.query(models.CareTeamRequest).filter(
        models.CareTeamRequest.doctor_id == current_doctor.id,
        models.CareTeamRequest.user_id == user_id,
        models.CareTeamRequest.status == "Pending"
    ).delete()
    
    db.commit()
    
    return {"message": "Patient removed successfully"}

# ==========================================
# 17. WITHDRAW PENDING REQUEST
# ==========================================
@doctor_data_router.delete("/pending-requests/{request_id}")
def withdraw_pending_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_doctor: models.Doctor = Depends(get_current_doctor)
):
    """Allows a doctor to cancel a care team request before the patient accepts it."""
    req = db.query(models.CareTeamRequest).filter(
        models.CareTeamRequest.id == request_id,
        models.CareTeamRequest.doctor_id == current_doctor.id,
        models.CareTeamRequest.status == "Pending"
    ).first()

    if not req:
        raise HTTPException(status_code=404, detail="Pending request not found")

    db.delete(req)
    db.commit()
    return {"message": "Request withdrawn successfully"}