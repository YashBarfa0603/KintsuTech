"""
Generate test Supabase JWT tokens compatible with KintsuTech backend.
Usage:
    uv run python scripts/generate_token.py [--admin] [--email user@example.com] [--name "My Name"]
"""

import argparse
import datetime
import os
import uuid
import jwt
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")


def generate_token(
    user_id: str | None = None,
    email: str = "developer@kintsutech.com",
    name: str = "Test Developer",
    is_admin: bool = False,
    can_repair: bool = False,
    days_valid: int = 7,
) -> str:
    if not SUPABASE_JWT_SECRET:
        raise ValueError(
            "SUPABASE_JWT_SECRET is not configured in .env or environment variables. "
            "Please configure SUPABASE_JWT_SECRET in your .env file."
        )
    now = datetime.datetime.now(datetime.timezone.utc)
    uid = user_id or str(uuid.uuid4())
    payload = {
        "sub": uid,
        "email": email,
        "role": "authenticated",
        "aud": "authenticated",
        "iss": f"{SUPABASE_URL}/auth/v1" if SUPABASE_URL else None,
        "iat": int(now.timestamp()),
        "exp": int((now + datetime.timedelta(days=days_valid)).timestamp()),
        "app_metadata": {
            "provider": "email",
            "role": "admin" if is_admin else "developer",
            "can_repair": True if (is_admin or can_repair) else False,
        },
        "user_metadata": {
            "full_name": name,
            "avatar_url": f"https://api.dicebear.com/7.x/bottts/svg?seed={uid}",
        },
    }
    if not payload["iss"]:
        payload.pop("iss")

    return jwt.encode(payload, SUPABASE_JWT_SECRET, algorithm="HS256")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Supabase JWT access token for testing")
    parser.add_argument("--admin", action="store_true", help="Grant admin & repair capabilities")
    parser.add_argument("--email", default="developer@kintsutech.com", help="User email")
    parser.add_argument("--name", default="Test Developer", help="User full name")
    parser.add_argument("--days", type=int, default=7, help="Token validity duration in days")

    args = parser.parse_args()
    token = generate_token(email=args.email, name=args.name, is_admin=args.admin, days_valid=args.days)
    print("\nAuthorization Header:")
    print(f"Bearer {token}\n")
