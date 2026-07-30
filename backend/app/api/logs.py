from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
import datetime

from app.core.database import get_db
from app.models.models import AuditLog

router = APIRouter()

class AuditLogSchema(BaseModel):
    id: str
    timestamp: str
    action: str
    status: str
    threat_flag: bool
    details: str = None

    class Config:
        from_attributes = True

@router.get("/audit", response_model=List[AuditLogSchema])
def get_audit_logs(limit: int = 50, db: Session = Depends(get_db)):
    logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit).all()
    result = []
    for log in logs:
        ts_str = log.timestamp.isoformat() if log.timestamp else ""
        if ts_str and not ts_str.endswith('Z') and '+' not in ts_str:
            ts_str += 'Z'
        result.append({
            "id": log.id,
            "timestamp": ts_str,
            "action": log.action,
            "status": log.status,
            "threat_flag": log.threat_flag,
            "details": log.details
        })
    return result
