"""Revocable opaque bearer sessions. Only SHA-256 token digests are stored."""
import argparse
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from fastapi import Depends, HTTPException, Request


def token_digest(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


class SessionRepository:
    def authenticate(self, token):
        with psycopg.connect(connect_timeout=3) as connection:
            connection.execute("SET LOCAL statement_timeout = '5s'")
            return connection.execute("""
                SELECT actor_id, role FROM api_reviewer_sessions
                WHERE token_hash = %s AND revoked_at IS NULL AND expires_at > CURRENT_TIMESTAMP
            """, (token_digest(token),)).fetchone()


def sessions():
    return SessionRepository()


def require_reviewer(request: Request, repo=Depends(sessions)):
    headers = request.headers.getlist("authorization")
    if len(headers) != 1:
        raise HTTPException(401, "Bearer session required", headers={"WWW-Authenticate": "Bearer"})
    match = re.fullmatch(r"(?i:Bearer) ([A-Za-z0-9_-]{43})", headers[0])
    principal = repo.authenticate(match[1]) if match else None
    if principal is None:
        raise HTTPException(401, "Invalid or expired session", headers={"WWW-Authenticate": "Bearer"})
    if principal[1] != "reviewer":
        raise HTTPException(403, "Reviewer role required")
    return principal[0]


def issue_session(connection, actor_id, *, hours=8, role="reviewer"):
    if not 1 <= hours <= 24 or role not in {"reviewer", "viewer"}:
        raise ValueError("Sessions require a supported role and 1–24 hour lifetime")
    token, session_id = secrets.token_urlsafe(32), uuid4()
    now = datetime.now(timezone.utc)
    connection.execute("""
        INSERT INTO api_reviewer_sessions(id, token_hash, actor_id, role, created_at, expires_at)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (session_id, token_digest(token), actor_id, role, now, now + timedelta(hours=hours)))
    return session_id, token


def main():
    parser = argparse.ArgumentParser(description="Administrative reviewer session management")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate")
    issue = commands.add_parser("issue")
    issue.add_argument("--actor-id", type=UUID, required=True)
    issue.add_argument("--hours", type=int, choices=range(1, 25), default=8)
    revoke = commands.add_parser("revoke")
    revoke.add_argument("--session-id", type=UUID, required=True)
    args = parser.parse_args()
    with psycopg.connect(connect_timeout=3) as connection:
        if args.command == "migrate":
            connection.execute((Path(__file__).parent / "sql/003_review_workflow.sql").read_text(encoding="utf-8"))
        elif args.command == "issue":
            session_id, token = issue_session(connection, args.actor_id, hours=args.hours)
        else:
            connection.execute("UPDATE api_reviewer_sessions SET revoked_at = CURRENT_TIMESTAMP WHERE id = %s", (args.session_id,))
    # Print only after commit succeeds. This is intentional secret delivery, not an application log.
    if args.command == "issue":
        print(f"Session ID: {session_id}\nBearer token (shown once): {token}")


if __name__ == "__main__":
    main()
