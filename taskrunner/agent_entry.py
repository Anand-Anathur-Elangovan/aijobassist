"""
VantaHire Agent — Entry Point for Packaged Executable
Handles first-time setup (API key), then starts the task runner.
"""

import os
import sys
import json
import hashlib
import getpass
import requests

# ── Config file path ──────────────────────────────────────────
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".vantahire")
CONFIG_FILE = os.path.join(CONFIG_DIR, "agent.json")

SUPABASE_URL = "https://feqhdpxnzlctpwvvjxui.supabase.co"


def load_config():
    """Load saved agent configuration."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return None


def save_config(config: dict):
    """Save agent configuration to disk."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def verify_key(api_key: str):
    """Verify the API key against Supabase and return user info."""
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    # Look up the key hash via service — we use the anon key + RPC
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/agent_keys?key_hash=eq.{key_hash}&is_active=eq.true&select=user_id",
        headers={
            "apikey": os.environ.get(
                "SUPABASE_ANON_KEY",
                "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZlcWhkcHhuemxjdHB3dnZqeHVpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQxMDczMjUsImV4cCI6MjA4OTY4MzMyNX0.aa7t-5sLixSpAkJwSEL4Ki-Uae2PFNyH9GHpMdFarOA"
            ),
            "Authorization": f"Bearer {os.environ.get('SUPABASE_SERVICE_ROLE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZlcWhkcHhuemxjdHB3dnZqeHVpIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NDEwNzMyNSwiZXhwIjoyMDg5NjgzMzI1fQ.LDv5jcFnSgMEha9SkWPaCohxgQsJwH64FeQXDx4x5nk')}",
        },
    )

    if resp.status_code != 200 or not resp.json():
        return None

    user_id = resp.json()[0]["user_id"]

    # Get user email from auth.users via user_profiles
    profile_resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/user_profiles?user_id=eq.{user_id}&select=full_name",
        headers={
            "apikey": os.environ.get(
                "SUPABASE_ANON_KEY",
                "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZlcWhkcHhuemxjdHB3dnZqeHVpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQxMDczMjUsImV4cCI6MjA4OTY4MzMyNX0.aa7t-5sLixSpAkJwSEL4Ki-Uae2PFNyH9GHpMdFarOA"
            ),
            "Authorization": f"Bearer {os.environ.get('SUPABASE_SERVICE_ROLE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZlcWhkcHhuemxjdHB3dnZqeHVpIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NDEwNzMyNSwiZXhwIjoyMDg5NjgzMzI1fQ.LDv5jcFnSgMEha9SkWPaCohxgQsJwH64FeQXDx4x5nk')}",
        },
    )

    name = ""
    if profile_resp.ok and profile_resp.json():
        name = profile_resp.json()[0].get("full_name", "")

    # Update last_used timestamp
    requests.patch(
        f"{SUPABASE_URL}/rest/v1/agent_keys?key_hash=eq.{key_hash}",
        headers={
            "apikey": os.environ.get(
                "SUPABASE_ANON_KEY",
                "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZlcWhkcHhuemxjdHB3dnZqeHVpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQxMDczMjUsImV4cCI6MjA4OTY4MzMyNX0.aa7t-5sLixSpAkJwSEL4Ki-Uae2PFNyH9GHpMdFarOA"
            ),
            "Authorization": f"Bearer {os.environ.get('SUPABASE_SERVICE_ROLE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZlcWhkcHhuemxjdHB3dnZqeHVpIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NDEwNzMyNSwiZXhwIjoyMDg5NjgzMzI1fQ.LDv5jcFnSgMEha9SkWPaCohxgQsJwH64FeQXDx4x5nk')}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json={"last_used": "now()"},
    )

    return {"user_id": user_id, "name": name}


def setup_wizard():
    """First-time setup: prompt for API key."""
    print()
    print("=" * 50)
    print("  VantaHire Agent Setup")
    print("=" * 50)
    print()
    print("  Get your API key from:")
    print("  https://vantahire.com/agent")
    print()

    while True:
        api_key = input("  Enter your API key: ").strip()
        if not api_key.startswith("vh_"):
            print("  ✗ Invalid key format. Keys start with 'vh_'")
            continue

        print("  Verifying...")
        user_info = verify_key(api_key)
        if not user_info:
            print("  ✗ Invalid or revoked key. Try again.")
            continue

        # Save config
        save_config({
            "api_key": api_key,
            "user_id": user_info["user_id"],
            "supabase_url": SUPABASE_URL,
        })

        print(f"  ✓ Connected to VantaHire")
        print(f"  ✓ Account: {user_info.get('name', 'User')}")
        print()
        return user_info["user_id"]


def main():
    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║          VantaHire — Desktop Agent               ║")
    print("║          Job Application Automation              ║")
    print("╚══════════════════════════════════════════════════╝")

    # Check for saved config
    config = load_config()

    if config and config.get("api_key"):
        # Verify saved key is still valid
        print("\n  Connecting with saved key...")
        user_info = verify_key(config["api_key"])
        if user_info:
            print(f"  ✓ Connected as {user_info.get('name', 'User')}")
            user_id = user_info["user_id"]
        else:
            print("  ✗ Saved key is expired or revoked.")
            os.remove(CONFIG_FILE)
            user_id = setup_wizard()
    else:
        user_id = setup_wizard()

    # Set env vars for the task runner
    config = load_config()
    os.environ["SUPABASE_URL"] = config.get("supabase_url", SUPABASE_URL)
    os.environ["AGENT_USER_ID"] = user_id

    # Point Playwright to system-installed browsers (not the .exe temp dir)
    if not os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        default_pw = os.path.join(os.path.expanduser("~"), "AppData", "Local", "ms-playwright")
        if os.path.isdir(default_pw):
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = default_pw
        else:
            print("  ⚠ Playwright browsers not found. Run: playwright install")
            print(f"    Expected at: {default_pw}")

    # Now start the actual task runner
    print()
    print("=" * 50)
    print("  Agent is running. Waiting for tasks...")
    print("  Press Ctrl+C to stop.")
    print("=" * 50)
    print()

    # Import and run main loop
    # (works both in packaged .exe and when run from source)
    sys.path.insert(0, os.path.dirname(__file__))
    from main import main as run_main
    run_main()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Agent stopped. Goodbye!")
        sys.exit(0)
