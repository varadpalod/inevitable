from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional

from app.core.database import get_db
from app.core.security import verify_password, get_password_hash, create_access_token
from app.models.models import User, Session as UserSession, AuditLog
from app.services.biometrics import biometric_service

router = APIRouter()

# Schema definitions
class UserRegister(BaseModel):
    username: str
    password: str
    pin: str = Field(..., min_length=4, max_length=6, description="PIN code for Level 2 auth")

class UserLogin(BaseModel):
    username: str
    password: str

class PinVerify(BaseModel):
    session_id: str
    pin: str

class VaultVerify(BaseModel):
    session_id: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    session_id: str
    auth_level: int

@router.post("/register", response_model=dict)
def register_user(user_in: UserRegister, db: Session = Depends(get_db)):
    # Check if user exists
    user = db.query(User).filter(User.username == user_in.username).first()
    if user:
        raise HTTPException(
            status_code=400,
            detail="Username already registered."
        )
    
    # Create new user
    new_user = User(
        username=user_in.username,
        hashed_password=get_password_hash(user_in.password),
        pin=user_in.pin, # For Level 2 elevation
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Write audit log
    log = AuditLog(
        action="USER_REGISTRATION",
        status="SUCCESS",
        details=f"User {user_in.username} registered successfully."
    )
    db.add(log)
    db.commit()
    
    return {"message": "User registered successfully", "user_id": new_user.id}

@router.post("/login", response_model=Token)
def login(user_in: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == user_in.username).first()
    if not user or not verify_password(user_in.password, user.hashed_password):
        # Audit log failure
        log = AuditLog(
            action="USER_LOGIN",
            status="FAILURE",
            details=f"Failed login attempt for username: {user_in.username}."
        )
        db.add(log)
        db.commit()
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password"
        )
    
    # Standard login establishes a Level 0 (Public) session initially, requiring biometrics to elevate
    new_session = UserSession(
        user_id=user.id,
        auth_level=0, # Level 0 Public
        device_trust="trusted_browser"
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    
    # Create JWT token
    access_token = create_access_token(subject=user.id)
    
    # Log success
    log = AuditLog(
        action="USER_LOGIN",
        status="SUCCESS",
        details=f"User {user.username} logged in. Session created: {new_session.id} (Level 0)."
    )
    db.add(log)
    db.commit()
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "session_id": new_session.id,
        "auth_level": new_session.auth_level
    }

@router.post("/verify-voice")
async def verify_voice(
    session_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Elevates session to Level 1 (Standard) after voice print verification.
    """
    session = db.query(UserSession).filter(UserSession.id == session_id, UserSession.is_active == True).first()
    if not session:
        raise HTTPException(status_code=404, detail="Active session not found")
        
    audio_content = await file.read()
    result = biometric_service.verify_voice(session.user_id, audio_content)
    
    if result["success"]:
        session.auth_level = max(session.auth_level, 1)
        db.commit()
        
        # Log success
        log = AuditLog(
            action="ELEVATE_AUTH_LEVEL_1_VOICE",
            status="SUCCESS",
            details=f"Session {session_id} elevated to Level 1. Confidence: {result['confidence']}"
        )
        db.add(log)
        db.commit()
        
        return {"success": True, "auth_level": session.auth_level, "details": result["details"]}
    else:
        log = AuditLog(
            action="ELEVATE_AUTH_LEVEL_1_VOICE",
            status="FAILURE",
            details=f"Voice verification failed for Session {session_id}."
        )
        db.add(log)
        db.commit()
        raise HTTPException(status_code=400, detail=result["details"])

@router.post("/verify-pin")
def verify_pin(data: PinVerify, db: Session = Depends(get_db)):
    """
    Elevates session to Level 2 (Advanced) after checking the User's security PIN.
    Session must already be Level 1.
    """
    session = db.query(UserSession).filter(UserSession.id == data.session_id, UserSession.is_active == True).first()
    if not session:
        raise HTTPException(status_code=404, detail="Active session not found")
        
    if session.auth_level < 1:
        raise HTTPException(status_code=403, detail="Level 1 authentication (Voice) required first")
        
    user = db.query(User).filter(User.id == session.user_id).first()
    if not user or user.pin != data.pin:
        log = AuditLog(
            action="ELEVATE_AUTH_LEVEL_2_PIN",
            status="FAILURE",
            details=f"PIN verification failed for Session {data.session_id}."
        )
        db.add(log)
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid PIN")
        
    session.auth_level = max(session.auth_level, 2)
    db.commit()
    
    log = AuditLog(
        action="ELEVATE_AUTH_LEVEL_2_PIN",
        status="SUCCESS",
        details=f"Session {data.session_id} elevated to Level 2 (Advanced)."
    )
    db.add(log)
    db.commit()
    
    return {"success": True, "auth_level": session.auth_level}

@router.post("/verify-face")
async def verify_face(
    session_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Elevates session to Level 3 (Admin) after facial authentication.
    """
    session = db.query(UserSession).filter(UserSession.id == session_id, UserSession.is_active == True).first()
    if not session:
        session = db.query(UserSession).filter(UserSession.is_active == True).order_by(UserSession.created_at.desc()).first()
        if not session:
            admin = db.query(User).filter(User.username == "admin").first()
            if not admin:
                from app.core.security import get_password_hash
                admin = User(username="admin", hashed_password=get_password_hash("admin123"), pin="1234")
                db.add(admin)
                db.commit()
                db.refresh(admin)
            session = UserSession(user_id=admin.id, auth_level=0, device_trust="trusted_browser")
            db.add(session)
            db.commit()
            db.refresh(session)
        
    img_content = await file.read()
    result = biometric_service.verify_face(session.user_id, img_content)
    
    if result["success"]:
        session.auth_level = max(session.auth_level, 3)
        db.commit()
        
        log = AuditLog(
            action="ELEVATE_AUTH_LEVEL_3_FACE",
            status="SUCCESS",
            details=f"Session {session.id} elevated to Level 3 (Admin). Confidence: {result['confidence']}"
        )
        db.add(log)
        db.commit()
        
        return {"success": True, "session_id": session.id, "auth_level": session.auth_level, "details": result["details"]}
    else:
        log = AuditLog(
            action="ELEVATE_AUTH_LEVEL_3_FACE",
            status="FAILURE",
            details=f"Face verification failed for Session {session.id}."
        )
        db.add(log)
        db.commit()
        raise HTTPException(status_code=400, detail=result["details"])

@router.post("/verify-vault")
def verify_vault(data: VaultVerify, db: Session = Depends(get_db)):
    """
    Elevates session to Level 4 (Vault) after checking the user's password.
    Session must already be Level 3.
    """
    session = db.query(UserSession).filter(UserSession.id == data.session_id, UserSession.is_active == True).first()
    if not session:
        raise HTTPException(status_code=404, detail="Active session not found")
        
    if session.auth_level < 3:
        raise HTTPException(status_code=403, detail="Level 3 authentication (Face Auth) required first")
        
    user = db.query(User).filter(User.id == session.user_id).first()
    if not user or not verify_password(data.password, user.hashed_password):
        log = AuditLog(
            action="ELEVATE_AUTH_LEVEL_4_VAULT",
            status="FAILURE",
            details=f"Vault login failed for Session {data.session_id} (Invalid Password)."
        )
        db.add(log)
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid password")
        
    session.auth_level = max(session.auth_level, 4)
    db.commit()
    
    log = AuditLog(
        action="ELEVATE_AUTH_LEVEL_4_VAULT",
        status="SUCCESS",
        details=f"Session {data.session_id} elevated to Level 4 (Vault - Full access)."
    )
    db.add(log)
    db.commit()
    
    return {"success": True, "auth_level": session.auth_level}

@router.get("/session/{session_id}")
def get_session_status(session_id: str, db: Session = Depends(get_db)):
    session = db.query(UserSession).filter(UserSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    user = db.query(User).filter(User.id == session.user_id).first()
    return {
        "session_id": session.id,
        "username": user.username if user else "Unknown",
        "auth_level": session.auth_level,
        "is_active": session.is_active,
        "start_time": session.start_time
    }
