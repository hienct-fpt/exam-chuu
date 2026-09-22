"""Grant / revoke the `admin` custom claim (parent account).

usage: python scripts/set_admin.py parent@gmail.com [--revoke] [--project PROJECT_ID]
The user must have signed in to the app at least once.
"""
from __future__ import annotations

import argparse

import firebase_admin
from firebase_admin import auth, credentials


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("email")
    ap.add_argument("--revoke", action="store_true")
    ap.add_argument("--project", default=None)
    args = ap.parse_args()
    firebase_admin.initialize_app(credentials.ApplicationDefault(), {"projectId": args.project} if args.project else None)
    user = auth.get_user_by_email(args.email)
    claims = dict(user.custom_claims or {})
    if args.revoke:
        claims.pop("admin", None)
    else:
        claims["admin"] = True
    auth.set_custom_user_claims(user.uid, claims)
    print(f"[admin] {args.email} ({user.uid}) claims={claims}. User must sign out/in to refresh token.")


if __name__ == "__main__":
    main()
