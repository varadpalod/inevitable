import logging
import json
import re
from sqlalchemy.orm import Session
from app.models.models import Memory
from app.core.config import settings

logger = logging.getLogger(__name__)

class MemoryService:
    def __init__(self):
        # We check if we can configure Gemini for extraction
        self.use_llm = bool(settings.GEMINI_API_KEY)
        if self.use_llm:
            import google.generativeai as genai
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        else:
            self.model = None

    def retrieve_memories(self, db: Session, session_id: str, prompt: str) -> str:
        """
        Retrieves relevant user facts and preferences for a given prompt from the database.
        Uses keyword matching as a lightweight search mechanism.
        """
        try:
            # 1. Fetch all memories for the session
            all_memories = db.query(Memory).filter(Memory.session_id == session_id).all()
            if not all_memories:
                return ""

            # 2. Extract keywords from the prompt (lowercase, alphanumeric, len > 3)
            words = re.findall(r'\b\w{4,}\b', prompt.lower())
            stop_words = {"what", "when", "where", "which", "who", "whom", "this", "that", "these", "those", "have", "with"}
            keywords = [w for w in words if w not in stop_words]

            relevant = []
            seen = set()

            # 3. Match memories by keywords
            for mem in all_memories:
                mem_content_lower = mem.content.lower()
                # If any keyword matches, or if it is a general preference we always include
                if any(kw in mem_content_lower for kw in keywords) or mem.entity_type == "preference":
                    if mem.content not in seen:
                        relevant.append(mem)
                        seen.add(mem.content)

            # Fallback: if no keyword match but we have preferences/facts, return the 3 most recent ones
            if not relevant:
                relevant = all_memories[-3:]

            if not relevant:
                return ""

            context_lines = []
            for r in relevant:
                context_lines.append(f"- [{r.entity_type.upper()}] {r.content}")
            
            context_str = "Retrieved User Context (Memory):\n" + "\n".join(context_lines)
            logger.info(f"Retrieved {len(relevant)} memories for session {session_id}")
            return context_str
        except Exception as e:
            logger.error(f"Error retrieving memories: {e}")
            return ""

    def extract_and_save_memory(self, db: Session, session_id: str, prompt: str, response: str) -> list:
        """
        Analyzes the prompt and response to extract facts/preferences and save them to database.
        Uses Gemini if API key is active, otherwise falls back to regex patterns.
        """
        extracted = []
        try:
            if self.use_llm:
                extracted = self._extract_via_llm(prompt, response)
            else:
                extracted = self._extract_via_regex(prompt, response)

            saved = []
            for item in extracted:
                entity_type = item.get("entity_type", "fact")
                content = item.get("content", "").strip()
                if not content:
                    continue

                # Avoid duplicate memory in the same session
                exists = db.query(Memory).filter(
                    Memory.session_id == session_id,
                    Memory.content == content
                ).first()
                
                if not exists:
                    mem = Memory(
                        session_id=session_id,
                        entity_type=entity_type,
                        content=content
                    )
                    db.add(mem)
                    saved.append(item)
            
            if saved:
                db.commit()
                logger.info(f"Saved {len(saved)} new memories for session {session_id}")
            
            return saved
        except Exception as e:
            logger.error(f"Error in extract_and_save_memory: {e}")
            return []

    def _extract_via_llm(self, prompt: str, response: str) -> list:
        """
        Uses Gemini to extract structured facts/preferences.
        """
        extraction_prompt = f"""
        Analyze the following conversation turn between a user and an AI assistant.
        Identify any user facts, preferences, or settings that the assistant should remember for future sessions (e.g. user's programming preferences, file paths, visual styling, names, credentials).
        
        User prompt: "{prompt}"
        AI response: "{response}"
        
        Respond ONLY with a valid JSON array of objects, containing:
        - "entity_type": either "fact" or "preference"
        - "content": a brief, clear statement of what to remember (e.g. "User prefers Python over Java", "User theme preference is dark mode")
        
        If nothing permanent is found, return an empty array [].
        """
        try:
            res = self.model.generate_content(
                extraction_prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            return json.loads(res.text.strip())
        except Exception as e:
            logger.error(f"LLM memory extraction failed: {e}")
            # Fall back to regex
            return self._extract_via_regex(prompt, response)

    def _extract_via_regex(self, prompt: str, response: str) -> list:
        """
        Lightweight fallback matching patterns like "I prefer X", "remember that Y".
        """
        extracted = []
        lower_prompt = prompt.lower()
        
        # Pattern 1: "prefer <something>"
        prefer_match = re.search(r"\bi prefer\s+([^.!?]+)", lower_prompt)
        if prefer_match:
            extracted.append({
                "entity_type": "preference",
                "content": f"User prefers {prefer_match.group(1).strip()}"
            })

        # Pattern 2: "remember that <something>"
        remember_match = re.search(r"\bremember\s+(?:that\s+)?([^.!?]+)", lower_prompt)
        if remember_match:
            extracted.append({
                "entity_type": "fact",
                "content": f"User fact: {remember_match.group(1).strip()}"
            })

        # Pattern 3: "my favorite <something> is <something>"
        fav_match = re.search(r"\bmy favorite\s+([^.!?]+)\s+is\s+([^.!?]+)", lower_prompt)
        if fav_match:
            extracted.append({
                "entity_type": "preference",
                "content": f"User favorite {fav_match.group(1).strip()} is {fav_match.group(2).strip()}"
            })
            
        return extracted

memory_service = MemoryService()
