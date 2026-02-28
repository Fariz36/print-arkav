import argparse
import os
import sqlite3
from datetime import datetime, timezone

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or update a backend user")
    parser.add_argument("--team-name", required=True, help="Team name shown in printed header")
    parser.add_argument("--username", required=True, help="Username to create/update")
    parser.add_argument("--password", required=True, help="Plain-text password")
    args = parser.parse_args()

    load_dotenv()
    db_path = os.getenv("DB_PATH", "./data/print_jobs.db")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                team_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        cols = conn.execute("PRAGMA table_info(users)").fetchall()
        col_names = {c[1] for c in cols}
        if "team_name" not in col_names:
            conn.execute("ALTER TABLE users ADD COLUMN team_name TEXT")
            conn.execute("UPDATE users SET team_name = username WHERE team_name IS NULL OR team_name = ''")
        conn.execute(
            """
            INSERT INTO users (username, team_name, password_hash, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                team_name = excluded.team_name,
                password_hash = excluded.password_hash
            """,
            (
                args.username.strip(),
                args.team_name.strip(),
                generate_password_hash(args.password),
                utc_now_iso(),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    print(f"User upserted: username={args.username} team_name={args.team_name}")


if __name__ == "__main__":
    main()
