import datetime
import uuid
from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    username = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    voice_print_path = Column(String(255), nullable=True)
    pin = Column(String(10), nullable=True) # Pin for Level 2 authentication
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    sessions = relationship("Session", back_populates="user")

class Session(Base):
    __tablename__ = "sessions"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    start_time = Column(DateTime, default=datetime.datetime.utcnow)
    auth_level = Column(Integer, default=0) # 0 to 4
    device_trust = Column(String(100), default="trusted_browser")
    is_active = Column(Boolean, default=True)
    
    user = relationship("User", back_populates="sessions")
    memories = relationship("Memory", back_populates="session")

class Memory(Base):
    __tablename__ = "memories"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("sessions.id"), nullable=False)
    entity_type = Column(String(100), nullable=False) # e.g. "fact", "preference", "user_prompt"
    content = Column(Text, nullable=False)
    vector_id = Column(String(100), nullable=True) # reference to ChromaDB document
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    session = relationship("Session", back_populates="memories")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    timestamp = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    action = Column(String(255), nullable=False) # e.g., "EXECUTE_COMMAND", "AUTH_ATTEMPT"
    status = Column(String(100), nullable=False) # e.g., "SUCCESS", "FAILURE", "BLOCKED"
    threat_flag = Column(Boolean, default=False)
    details = Column(Text, nullable=True)
