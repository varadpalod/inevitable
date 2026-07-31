import logging
import json
import re
from typing import Dict, Any, List, Tuple
from app.services.agents import file_agent, browser_agent, coding_agent, vault_agent
from app.core.config import settings

logger = logging.getLogger(__name__)

class AegisPlanner:
    def __init__(self):
        self.use_llm = bool(settings.GEMINI_API_KEY)
        if self.use_llm:
            import google.generativeai as genai
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        else:
            self.model = None

    def plan_and_execute(self, prompt: str, session_level: int) -> Tuple[str, str, int, List[str]]:
        """
        Decomposes the prompt, checks permission levels, executes agent tools,
        and aggregates outputs.
        Returns:
            status: "SUCCESS" | "BLOCKED" | "UPGRADE_REQUIRED"
            response: The consolidated agent text response
            required_level: The maximum level required for this workflow
            steps_log: An execution trace list for UI visualization
        """
        steps_log = ["[Planner] Initializing Project AEGIS task planning..."]
        
        # 1. Decompose the request into steps
        try:
            if self.use_llm:
                steps = self._decompose_via_llm(prompt)
            else:
                steps = self._decompose_via_rules(prompt)
        except Exception as e:
            logger.error(f"Planner decomposition error: {e}")
            steps = self._decompose_via_rules(prompt)

        steps_log.append(f"[Planner] Request decomposed into {len(steps)} sub-task(s).")
        
        # 2. Determine max security level required and validate
        max_required_level = 0
        for step in steps:
            req_level = self._get_required_level(step)
            max_required_level = max(max_required_level, req_level)
            
        steps_log.append(f"[Security Gateway] Authentication Check: Required Level {max_required_level} | Session Level {session_level}")
        
        if session_level < max_required_level:
            steps_log.append(f"[Security Gateway] BLOCKED: Elevation to Level {max_required_level} is required.")
            return "UPGRADE_REQUIRED", f"Authentication required: Unlocking this operation requires Level {max_required_level} authorization.", max_required_level, steps_log

        # 3. Execute each step
        results = []
        for idx, step in enumerate(steps):
            agent_type = step.get("agent")
            action = step.get("action")
            args = step.get("args", {})
            desc = step.get("description", f"Executing task {idx + 1}")
            
            steps_log.append(f"[Agent Router] Dispatching Step {idx + 1}: {desc}")
            
            agent_output = ""
            if agent_type == "file":
                filename = args.get("filename", "default.txt")
                content = args.get("content", "")
                agent_output = file_agent.execute(action, filename, content)
            elif agent_type == "browser":
                query = args.get("query", "")
                agent_output = browser_agent.execute(action, query)
            elif agent_type == "coding":
                code = args.get("code", "")
                agent_output = coding_agent.execute(action, code)
            elif agent_type == "vault":
                agent_output = vault_agent.execute(action)
            else:
                # Chat or generic response
                agent_output = f"[Assistant] Processing response..."
                
            steps_log.append(f"[Execution Layer] Step {idx + 1} completed: {agent_output.splitlines()[0] if agent_output else 'No output'}")
            results.append({
                "step": desc,
                "output": agent_output
            })

        # 4. Consolidate responses
        steps_log.append("[Planner] Consolidating execution results...")
        final_response = ""
        if self.use_llm:
            final_response = self._consolidate_via_llm(prompt, results)
        else:
            consolidated_parts = [r['output'] for r in results if r.get('output')]
            final_response = "\n\n".join(consolidated_parts)
            
        steps_log.append("[Planner] Pipeline execution finished.")
        return "SUCCESS", final_response, max_required_level, steps_log

    def _get_required_level(self, step: Dict[str, Any]) -> int:
        """
        Retrieves the exact RBAC level required for a specific agent action.
        """
        agent = step.get("agent")
        action = step.get("action")
        
        if agent == "vault":
            return 4
        if agent == "coding" and action == "run":
            return 2
        if agent == "file":
            if action in ["write", "delete"]:
                return 2
            elif action == "read":
                return 1
        # Public / General chat / web search
        return 0

    def _decompose_via_llm(self, prompt: str) -> List[Dict[str, Any]]:
        decomposition_prompt = f"""
        Decompose the following user command for Project AEGIS into a sequence of execution steps.
        Each step must be routed to one of the following agents:
        - "file": action is "read", "write", or "delete". Arguments: "filename", "content" (for write).
        - "browser": action is "search" or "extract". Arguments: "query".
        - "coding": action is "run" or "lint". Arguments: "code".
        - "vault": action is "read_secrets". Arguments: none.
        - "assistant": action is "chat". Arguments: none.
        
        User command: "{prompt}"
        
        Respond ONLY with a valid JSON array of step objects:
        [
          {{
            "agent": "file" / "browser" / "coding" / "vault" / "assistant",
            "action": "read" / "write" / "delete" / "search" / "run" / "read_secrets" / "chat",
            "args": {{ "filename": "example.txt", ... }},
            "description": "Short summary of the step"
          }}
        ]
        """
        try:
            res = self.model.generate_content(
                decomposition_prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            return json.loads(res.text.strip())
        except Exception as e:
            logger.error(f"LLM decomposition failed: {e}")
            return self._decompose_via_rules(prompt)

    def _decompose_via_rules(self, prompt: str) -> List[Dict[str, Any]]:
        """
        Regex-based rule engine to compile prompts into agent steps (Mock fallback).
        """
        lower = prompt.lower()
        steps = []
        
        # 1. Vault check
        if any(w in lower for w in ["vault", "secret", "credentials", "api key"]):
            steps.append({
                "agent": "vault",
                "action": "read_secrets",
                "args": {},
                "description": "Retrieving encrypted secrets from Secure Vault"
            })
            return steps

        # 2. File write/delete check
        write_match = re.search(r"write\s+(?:to\s+)?(?:file\s+)?([\w.-]+)(?:\s+with\s+data\s+|\s+content\s+)?(.*)", lower)
        if write_match:
            filename = write_match.group(1).strip()
            content = write_match.group(2).strip() or "Sample payload data."
            steps.append({
                "agent": "file",
                "action": "write",
                "args": {"filename": filename, "content": content},
                "description": f"Writing payload contents to file '{filename}' inside sandbox"
            })
            return steps

        delete_match = re.search(r"delete\s+(?:file\s+)?([\w.-]+)", lower)
        if delete_match:
            filename = delete_match.group(1).strip()
            steps.append({
                "agent": "file",
                "action": "delete",
                "args": {"filename": filename},
                "description": f"Removing file '{filename}' from sandbox"
            })
            return steps

        # 3. File read check
        read_match = re.search(r"read\s+(?:file\s+)?([\w.-]+)", lower)
        if read_match:
            filename = read_match.group(1).strip()
            steps.append({
                "agent": "file",
                "action": "read",
                "args": {"filename": filename},
                "description": f"Reading file contents of '{filename}' from sandbox"
            })
            return steps

        # 4. Code running check
        if any(w in lower for w in ["run code", "execute code", "run python", "run script"]):
            steps.append({
                "agent": "coding",
                "action": "run",
                "args": {"code": "print('Initializing agent checks...')\nprint('Done.')"},
                "description": "Executing script inside safe python virtual environment container"
            })
            return steps

        # 5. Browser search
        if any(w in lower for w in ["weather", "search", "browse", "news"]):
            steps.append({
                "agent": "browser",
                "action": "search",
                "args": {"query": prompt},
                "description": f"Executing web search browser agent for query: '{prompt}'"
            })
            return steps

        # Default: general assistant chatbot
        steps.append({
            "agent": "assistant",
            "action": "chat",
            "args": {},
            "description": "Answering general query using AI core"
        })
        return steps

    def _consolidate_via_llm(self, original_prompt: str, results: List[Dict[str, Any]]) -> str:
        prompt_context = "\n".join([f"Agent Step: {r['step']}\nOutput: {r['output']}" for r in results])
        consolidation_prompt = f"""
        Consolidate the following agent execution results into a concise, professional answer for the user.
        Do not make up information; base the response strictly on the agent output.
        
        Original User Command: "{original_prompt}"
        
        Agent Execution Logs:
        {prompt_context}
        
        Consolidated Response:
        """
        try:
            res = self.model.generate_content(consolidation_prompt)
            return res.text
        except Exception as e:
            logger.error(f"Consolidation via LLM failed: {e}")
            return f"Agent execution successful.\nResults:\n" + "\n".join([r["output"] for r in results])

planner_service = AegisPlanner()
