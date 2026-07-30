import os
import logging
import shutil
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Sandbox configuration
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SANDBOX_DIR = os.path.join(BASE_DIR, "sandbox")

def verify_sandbox_path(filename: str) -> str:
    """
    Prevents path traversal by ensuring the resolved file path lies strictly within the sandbox directory.
    """
    # Create sandbox dir if it does not exist
    if not os.path.exists(SANDBOX_DIR):
        os.makedirs(SANDBOX_DIR)
        
    # Resolve absolute paths
    abs_sandbox = os.path.abspath(SANDBOX_DIR)
    target_path = os.path.abspath(os.path.join(SANDBOX_DIR, filename))
    
    if not target_path.startswith(abs_sandbox):
        raise PermissionError(f"Security Alert: Directory traversal blocked. Path '{target_path}' is outside sandbox.")
        
    return target_path

class FileAgent:
    """
    File Agent: Handles file read, write, and delete operations inside the sandbox.
    """
    def execute(self, action: str, filename: str, content: str = "") -> str:
        try:
            target_path = verify_sandbox_path(filename)
            
            if action == "read":
                if not os.path.exists(target_path):
                    return f"[File Agent Error] File '{filename}' not found in sandbox."
                with open(target_path, "r", encoding="utf-8") as f:
                    data = f.read()
                return f"[File Agent] Successfully read '{filename}':\n\n{data}"
                
            elif action == "write":
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(content)
                return f"[File Agent] Successfully wrote data to '{filename}'."
                
            elif action == "delete":
                if not os.path.exists(target_path):
                    return f"[File Agent Error] File '{filename}' does not exist in sandbox."
                os.remove(target_path)
                return f"[File Agent] Successfully deleted '{filename}' from sandbox."
                
            else:
                return f"[File Agent Error] Unsupported action: {action}"
        except PermissionError as pe:
            logger.warning(str(pe))
            return f"[Security Block] {str(pe)}"
        except Exception as e:
            logger.error(f"File Agent error: {e}")
            return f"[File Agent Error] Operation failed: {str(e)}"

class BrowserAgent:
    """
    Browser Agent: Simulates Playwright-based automated web interactions and search.
    """
    def execute(self, action: str, query: str = "") -> str:
        logger.info(f"Browser Agent executing {action} for query: {query}")
        # Phase 1: Simulate high-fidelity browser actions.
        if action == "search":
            if "weather" in query.lower():
                return ("[Browser Agent] Navigated to weather forecast portal. Extracted data:\n"
                        "- Temperature: 22°C (Feels like 20°C)\n"
                        "- Condition: Overcast with light showers\n"
                        "- Humidity: 84%, Wind: 14 km/h West")
            elif "news" in query.lower():
                return ("[Browser Agent] Searched news aggregator. Top Headlines:\n"
                        "1. AI Agents Set to Automate Local Workstations in 2026\n"
                        "2. Cyber-security Frameworks Focus on Multi-Factor Biometrics")
            else:
                return f"[Browser Agent] Performed search for '{query}'. Found 3 matching articles. Content summarized: Relevant results loaded."
        elif action == "extract":
            return f"[Browser Agent] Navigation successful. Extracted DOM text from targeted URL. Length: 1240 characters."
        else:
            return f"[Browser Agent Error] Unknown browser action: {action}"

class CodingAgent:
    """
    Coding Agent: Simulates code execution and validation within the sandbox container context.
    """
    def execute(self, action: str, code: str = "") -> str:
        logger.info(f"Coding Agent executing {action}")
        if action == "run":
            # Simulate isolated container execution
            if "print" in code:
                # Basic mock execution of print statements
                lines = code.split("\n")
                output = []
                for line in lines:
                    if "print(" in line:
                        # Extract string between print("...")
                        content = line.split("print(")[1].rstrip(")")
                        if (content.startswith("'") and content.endswith("'")) or (content.startswith('"') and content.endswith('"')):
                            output.append(content[1:-1])
                        else:
                            output.append("3.14159 (evaluated expression)")
                return f"[Coding Agent] Execution Output:\n" + "\n".join(output)
            return "[Coding Agent] Executed python payload. Process returned exit code 0. Output: Success."
        elif action == "lint":
            return "[Coding Agent] Lint checks passed. 0 issues detected."
        else:
            return f"[Coding Agent Error] Unknown coding action: {action}"

class VaultAgent:
    """
    Vault Agent: Manages access to highly sensitive credentials/keys.
    Requires Level 4 authorization to be queried.
    """
    def execute(self, action: str) -> str:
        if action == "read_secrets":
            return (
                "[Vault Agent] Decrypting AES-256 Vault storage...\n"
                "Decryption Successful. Retrieved Environment Keys:\n"
                "--------------------------------------------------\n"
                "- OPENAI_API_KEY: sk-proj-...a8F9\n"
                "- STRIPE_API_SECRET: sk_live_...93d2\n"
                "- MASTER_DB_PASSWORD: super_secure_vault_pass_9988\n"
                "--------------------------------------------------"
            )
        else:
            return "[Vault Agent Error] Unsupported action."

# Instantiate agent singletons
file_agent = FileAgent()
browser_agent = BrowserAgent()
coding_agent = CodingAgent()
vault_agent = VaultAgent()
