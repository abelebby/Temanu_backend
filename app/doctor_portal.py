from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import date, timedelta
from app.database import get_db
from app import models, schemas
from app.auth import verify_password, create_doctor_access_token, get_current_doctor

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
        entry = {"timestamp": m.timestamp.isoformat() if m.timestamp else None}
        if m.heart_rate is not None:
            entry["heart_rate"] = m.heart_rate
        if m.blood_pressure_systolic is not None:
            entry["blood_pressure_systolic"] = m.blood_pressure_systolic
        if m.blood_pressure_diastolic is not None:
            entry["blood_pressure_diastolic"] = m.blood_pressure_diastolic
        if m.blood_glucose is not None:
            entry["blood_glucose"] = m.blood_glucose
        if m.oxygen_saturation is not None:
            entry["oxygen_saturation"] = m.oxygen_saturation
        if m.body_weight is not None:
            entry["body_weight"] = m.body_weight
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
# 9. GET MEDICAL RECORDS (filterable by patient)
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
