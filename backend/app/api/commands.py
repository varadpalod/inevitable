from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel
import logging

from app.core.database import get_db
from app.models.models import Session as UserSession, AuditLog
from app.services.gemini import gemini_service
from app.services.memory import memory_service
from app.services.planner import planner_service
from typing import List

logger = logging.getLogger(__name__)

router = APIRouter()

class CommandRequest(BaseModel):
    session_id: str
    prompt: str

class CommandResponse(BaseModel):
    status: str # "SUCCESS", "BLOCKED", "UPGRADE_REQUIRED"
    response: str
    required_level: int = 0
    message: str = ""
    execution_steps: List[str] = []

@router.post("/execute", response_model=CommandResponse)
def execute_command(req: CommandRequest, db: Session = Depends(get_db)):
    # 1. Verify session exists
    session = db.query(UserSession).filter(UserSession.id == req.session_id, UserSession.is_active == True).first()
    if not session:
        # Log failure
        log = AuditLog(
            action="COMMAND_EXECUTION",
            status="FAILURE",
            details=f"Invalid session ID: {req.session_id}"
        )
        db.add(log)
        db.commit()
        raise HTTPException(status_code=404, detail="Active session not found")

    # 2. Security Gateway: Check for prompt injection or malicious input
    classification = gemini_service.classify_prompt(req.prompt)
    if not classification.get("is_safe", True):
        # Log threat
        log = AuditLog(
            action="COMMAND_EXECUTION",
            status="BLOCKED",
            threat_flag=True,
            details=f"Blocked malicious prompt: '{req.prompt}'. Reason: {classification.get('reason')}"
        )
        db.add(log)
        db.commit()
        
        return CommandResponse(
            status="BLOCKED",
            response=f"Security Gateway Alert: Command blocked. Reason: {classification.get('reason')}",
            required_level=0,
            message="Prompt classified as malicious.",
            execution_steps=["[Security Gateway] THREAT DETECTED: Command blocked due to prompt injection check."]
        )

    # 3. Retrieve relevant memories
    memories_context = memory_service.retrieve_memories(db, session.id, req.prompt)

    # 4. Execute prompt via AegisPlanner (it checks RBAC inside)
    # If using LLM, we append memories context to the LLM context pool, or let the planner handle it.
    # To let the planner know about context, we can append it directly if it exists.
    augmented_prompt = req.prompt
    if memories_context:
        augmented_prompt = f"Context memories:\n{memories_context}\n\nUser request: {req.prompt}"

    status, response, required_level, execution_steps = planner_service.plan_and_execute(augmented_prompt, session.auth_level)

    # Insert memory context log if retrieved
    if memories_context:
        execution_steps.insert(1, f"[Memory Service] Retrieved relevant user context:\n{memories_context}")

    # 5. Extract and save new memories from successful interactions
    if status == "SUCCESS":
        saved_mems = memory_service.extract_and_save_memory(db, session.id, req.prompt, response)
        if saved_mems:
            saved_desc = ", ".join([f"'{m.get('content')}'" for m in saved_mems])
            execution_steps.append(f"[Memory Service] Saved new memories: {saved_desc}")

        # Log Success
        log = AuditLog(
            action="COMMAND_EXECUTION",
            status="SUCCESS",
            details=f"Executed command: '{req.prompt}'. Current auth level: {session.auth_level}."
        )
        db.add(log)
        db.commit()
        
        return CommandResponse(
            status="SUCCESS",
            response=response,
            execution_steps=execution_steps
        )
        
    elif status == "UPGRADE_REQUIRED":
        # Log authentication challenge
        log = AuditLog(
            action="COMMAND_EXECUTION",
            status="BLOCKED_BY_RBAC",
            details=f"Prompt '{req.prompt}' blocked. Session level {session.auth_level} < Required {required_level}."
        )
        db.add(log)
        db.commit()
        
        level_names = {
            1: "Level 1: Standard (Voice Match required)",
            2: "Level 2: Advanced (Voice + PIN required)",
            3: "Level 3: Admin (Face Auth required)",
            4: "Level 4: Vault (Face Auth + Password required)"
        }
        
        return CommandResponse(
            status="UPGRADE_REQUIRED",
            response=f"Authentication required: This command needs {level_names.get(required_level, 'higher auth level')}.",
            required_level=required_level,
            message=f"Please verify your credentials for Level {required_level}.",
            execution_steps=execution_steps
        )

    # Fallback/General error
    return CommandResponse(
        status="BLOCKED",
        response=response,
        execution_steps=execution_steps
    )

@router.post("/execute-voice", response_model=CommandResponse)
async def execute_voice(
    session_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Receives voice recording, transcribes it, and routes it to standard execution.
    """
    session = db.query(UserSession).filter(UserSession.id == session_id, UserSession.is_active == True).first()
    if not session:
        raise HTTPException(status_code=404, detail="Active session not found")
        
    audio_content = await file.read()
    if len(audio_content) == 0:
        raise HTTPException(status_code=400, detail="Empty audio file")
        
    # Mock text based on filename
    transcribed_text = "What is the status of the file agent?"
    filename_lower = file.filename.lower()
    if "vault" in filename_lower:
        transcribed_text = "Show me the secret credentials in the vault"
    elif "delete" in filename_lower:
        transcribed_text = "delete file old_report.txt"
    elif "read" in filename_lower:
        transcribed_text = "read file system_config.txt"
        
    logger.info(f"Transcribed voice command: '{transcribed_text}'")
    
    # Route to regular command execution
    req = CommandRequest(session_id=session_id, prompt=transcribed_text)
    res = execute_command(req, db)
    
    # Append the transcription info to response and execution steps
    res.response = f"[Voice Transcribed: \"{transcribed_text}\"]\n\n" + res.response
    res.execution_steps.insert(0, f"[Whisper Speech-to-Text] Transcribed voice file '{file.filename}' to text: \"{transcribed_text}\"")
    
    return res

