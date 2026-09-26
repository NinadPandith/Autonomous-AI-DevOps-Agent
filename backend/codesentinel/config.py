"""Central configuration, loaded from backend/.env."""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

load_dotenv(BACKEND_DIR / ".env")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")  # gemini | claude
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
# Tried in order when the current model's free-tier quota runs out or it is overloaded.
GEMINI_FALLBACK_MODELS = [m.strip() for m in os.getenv(
    "GEMINI_FALLBACK_MODELS", "gemini-3.5-flash,gemini-3-flash-preview,gemini-3.1-flash-lite"
).split(",") if m.strip()]
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5")
CLAUDE_EFFORT = os.getenv("CLAUDE_EFFORT", "high")  # low | medium | high | xhigh | max
DATABASE_PATH = BACKEND_DIR / os.getenv("DATABASE_PATH", "codesentinel.db")
MAX_FIX_ATTEMPTS = int(os.getenv("MAX_FIX_ATTEMPTS", "3"))
RUN_TIME_LIMIT_S = int(os.getenv("RUN_TIME_LIMIT_S", "600"))
FRONTEND_ORIGINS = [o.strip() for o in os.getenv("FRONTEND_ORIGINS", "http://localhost:5180,http://127.0.0.1:5180").split(",") if o.strip()]
# Run the agent on user-pasted GitHub repos. This installs and executes their code on this machine.
ALLOW_USER_REPOS = os.getenv("ALLOW_USER_REPOS", "false").lower() == "true"
# Protects the free LLM quota on a public deployment. 0 = unlimited.
MAX_RUNS_PER_DAY = int(os.getenv("MAX_RUNS_PER_DAY", "0"))
# Limits for user-provided repositories.
USER_REPO_MAX_MB = int(os.getenv("USER_REPO_MAX_MB", "50"))
CLONE_TIMEOUT_S = int(os.getenv("CLONE_TIMEOUT_S", "90"))
INSTALL_TIMEOUT_S = int(os.getenv("INSTALL_TIMEOUT_S", "300"))

DEMO_REPO_PATH = PROJECT_ROOT / "demo-repo"
WORKSPACES_DIR = PROJECT_ROOT / "workspaces"
