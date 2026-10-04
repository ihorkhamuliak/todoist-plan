"""Store the Todoist API token from the clipboard in Windows Credential Manager, then clear the clipboard.

Why not getpass: in the VS Code terminal Ctrl+V does not reach a hidden prompt, and an empty token is saved silently.
The token is never printed. Copy it in Todoist: Settings → Integrations → Developer → API token, then run this.
"""
import re, subprocess, sys
import keyring
from todoist_api_python.api import TodoistAPI

sys.stdout.reconfigure(encoding="utf-8")
ps = ["powershell", "-NoProfile", "-Command"]
tok = subprocess.run(ps + ["Get-Clipboard -Raw"], capture_output=True, text=True).stdout.strip()

if not re.fullmatch(r"[0-9a-f]{40}", tok):
    print(f"❌ clipboard does not hold a token (length {len(tok)}, expected 40 hex chars). Nothing saved.")
    sys.exit(1)

try:
    api = TodoistAPI(tok)  # keep a reference: without it the client closes before the request
    n = sum(len(page) for page in api.get_projects())
except Exception as e:
    print(f"❌ Todoist rejected the token ({type(e).__name__}). Nothing saved.")
    sys.exit(1)

keyring.set_password("todoist", "api", tok)
subprocess.run(ps + ["Set-Clipboard -Value ' '"])
ok = keyring.get_password("todoist", "api") == tok
print(f"✅ saved: {ok} · length {len(tok)} · projects visible: {n} · clipboard cleared")
