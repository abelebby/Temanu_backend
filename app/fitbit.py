import os
import base64
import requests
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.auth import get_current_user

router = APIRouter(prefix="/fitbit", tags=["Fitbit Integration"])

CLIENT_ID = os.getenv("FITBIT_CLIENT_ID")
CLIENT_SECRET = os.getenv("FITBIT_CLIENT_SECRET")
# NOTE: This must be your FASTAPI backend URL (e.g., https://your-backend.com/fitbit/callback)
REDIRECT_URI = os.getenv("FITBIT_REDIRECT_URI") 

# ==========================================
# 1. GENERATE THE LOGIN URL
# ==========================================
@router.get("/connect")
def connect_to_fitbit(current_user: models.User = Depends(get_current_user)):

    scopes = "activity"
    state = str(current_user.id)
    
    url = (
        f"https://www.fitbit.com/oauth2/authorize"
        f"?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope={scopes}"
        f"&state={state}" 
    )
    
    return {"auth_url": url}

# ==========================================
# 2. HANDLE THE CALLBACK FROM FITBIT
# ==========================================
@router.get("/callback")
def fitbit_callback(code: str, state: str, db: Session = Depends(get_db)):

    user_id = int(state) 

    auth_string = f"{CLIENT_ID}:{CLIENT_SECRET}"
    b64_auth = base64.b64encode(auth_string.encode()).decode()
    
    headers = {
        "Authorization": f"Basic {b64_auth}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    data = {
        "client_id": CLIENT_ID,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
        "code": code
    }
    
    response = requests.post("https://api.fitbit.com/oauth2/token", headers=headers, data=data)
    
    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to exchange token with Fitbit")
        
    token_data = response.json()
    
    # Save or update the tokens in database
    db_token = db.query(models.FitbitToken).filter(models.FitbitToken.user_id == user_id).first()
    
    if not db_token:
        db_token = models.FitbitToken(user_id=user_id)
        db.add(db_token)
        
    db_token.access_token = token_data["access_token"]
    db_token.refresh_token = token_data["refresh_token"]
    db_token.fitbit_user_id = token_data["user_id"]
    db.commit()

    frontend_return_url = "https://temanu.vercel.app"
    
    return RedirectResponse(url=frontend_return_url)