import os
import logging
import shutil
from typing import Dict, Any

logger = logging.getLogger(__name__)

# System and Sandbox configuration
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SANDBOX_DIR = os.path.join(BASE_DIR, "sandbox")

def resolve_system_path(filename: str) -> str:
    """
    Resolves file paths for system-wide read, write, and editing operations.
    Supports absolute paths (e.g. C:/Users/VARAD/...) and relative workspace/sandbox paths.
    """
    if not os.path.exists(SANDBOX_DIR):
        os.makedirs(SANDBOX_DIR)
        
    if os.path.isabs(filename):
        return os.path.abspath(filename)
    
    # Try resolving relative to sandbox first
    sandbox_path = os.path.abspath(os.path.join(SANDBOX_DIR, filename))
    if os.path.exists(sandbox_path):
        return sandbox_path
        
    # Fallback to root project workspace folder
    root_path = os.path.abspath(os.path.join(BASE_DIR, filename))
    if os.path.exists(root_path):
        return root_path
        
    return sandbox_path

class FileAgent:
    """
    File Agent: Performs system-wide file read, write, append, and edit operations.
    """
    def execute(self, action: str, filename: str, content: str = "") -> str:
        try:
            target_path = resolve_system_path(filename)
            
            # Ensure parent directories exist when writing
            parent_dir = os.path.dirname(target_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)
            
            if action == "read":
                if not os.path.exists(target_path):
                    return f"File '{filename}' not found on device."
                with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
                    data = f.read()
                return data
                
            elif action in ["write", "create"]:
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(content)
                return f"Successfully saved content to '{target_path}'."
                
            elif action in ["append", "edit"]:
                existing = ""
                if os.path.exists(target_path):
                    with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
                        existing = f.read()
                with open(target_path, "a", encoding="utf-8") as f:
                    if existing and not existing.endswith("\n"):
                        f.write("\n")
                    f.write(content)
                return f"Successfully updated and appended content to '{target_path}'."
                
            elif action == "delete":
                if not os.path.exists(target_path):
                    return f"File '{filename}' does not exist on device."
                os.remove(target_path)
                return f"Successfully deleted '{filename}' from device."
                
            else:
                return f"Unsupported action: {action}"
        except Exception as e:
            logger.error(f"File Agent error: {e}")
            return f"Error: File operation failed: {str(e)}"

class BrowserAgent:
    """
    Browser Agent: Simulates Playwright-based web interactions and search.
    """
    def execute(self, action: str, query: str = "") -> str:
        logger.info(f"Browser Agent executing {action} for query: {query}")
        if action == "search":
            if "weather" in query.lower():
                return ("Current Weather:\n"
                        "• Temperature: 22°C (Feels like 20°C)\n"
                        "• Condition: Overcast with light showers\n"
                        "• Humidity: 84%, Wind: 14 km/h West")
            elif "news" in query.lower():
                return ("Top News Headlines:\n"
                        "1. AI Agents Set to Automate Local Workstations in 2026\n"
                        "2. Cyber-security Frameworks Focus on Multi-Factor Biometrics")
            else:
                return f"Search results for '{query}': Relevant information retrieved successfully."
        elif action == "extract":
            return "Extracted web page content successfully."
        else:
            return f"Unknown browser action: {action}"

class CodingAgent:
    """
    Coding Agent: Simulates code execution and validation.
    """
    def execute(self, action: str, code: str = "") -> str:
        logger.info(f"Coding Agent executing {action}")
        if action == "run":
            if "print" in code:
                lines = code.split("\n")
                output = []
                for line in lines:
                    if "print(" in line:
                        content = line.split("print(")[1].rstrip(")")
                        if (content.startswith("'") and content.endswith("'")) or (content.startswith('"') and content.endswith('"')):
                            output.append(content[1:-1])
                        else:
                            output.append("3.14159")
                return "\n".join(output)
            return "Executed python payload successfully. Output: Success."
        elif action == "lint":
            return "Lint checks passed. 0 issues detected."
        else:
            return f"Unknown coding action: {action}"

class VaultAgent:
    """
    Vault Agent: Manages access to sensitive credentials/keys.
    """
    def execute(self, action: str) -> str:
        if action == "read_secrets":
            return (
                "Decrypted Environment Keys:\n"
                "- OPENAI_API_KEY: sk-proj-...a8F9\n"
                "- STRIPE_API_SECRET: sk_live_...93d2\n"
                "- MASTER_DB_PASSWORD: super_secure_vault_pass_9988"
            )
        else:
            return "Unsupported action."

# Instantiate agent singletons
file_agent = FileAgent()
browser_agent = BrowserAgent()
coding_agent = CodingAgent()
vault_agent = VaultAgent()
