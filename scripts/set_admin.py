#!/usr/bin/env python3
"""Set a user as admin in AgentFarm.

Usage:
    python scripts/set_admin.py <device_id>
    python scripts/set_admin.py --list  # List all users
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agentfarm.monetization.users import UserManager

def main():
    storage_dir = Path.home() / "agentfarm" / ".agentfarm"
    if not storage_dir.exists():
        storage_dir = Path(".agentfarm")

    user_manager = UserManager(storage_dir)

    if len(sys.argv) < 2:
        print("Usage: python scripts/set_admin.py <device_id>")
        print("       python scripts/set_admin.py --list")
        sys.exit(1)

    if sys.argv[1] == "--list":
        users = user_manager.list_users(limit=50)
        print(f"\n{'='*60}")
        print(f"  USERS ({len(users)} total)")
        print(f"{'='*60}")
        for user in users:
            admin_badge = " [ADMIN]" if user.is_admin else ""
            tier_badge = f" [{user.tier.value.upper()}]" if user.tier.value != "free" else ""
            prompts = f"{user.prompts_remaining} prompts" if user.prompts_remaining >= 0 else "unlimited"
            print(f"  {user.device_id[:16]}...{admin_badge}{tier_badge}")
            print(f"    Prompts: {prompts}, Used: {user.prompts_used_total}")
        print()
        sys.exit(0)

    device_id = sys.argv[1]
    is_admin = "--remove" not in sys.argv

    user = user_manager.set_admin(device_id, is_admin)
    print(f"\n{'='*60}")
    print(f"  User {device_id[:16]}...")
    print(f"  Admin: {user.is_admin}")
    print(f"  Tier: {user.tier.value}")
    print(f"  Prompts: {user.prompts_remaining}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
