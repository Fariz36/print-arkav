import argparse
import os
import sqlite3
from datetime import datetime, timezone

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_line(line: str):
    raw = line.strip().rstrip(",")
    if not raw:
        return None
    if " - " not in raw or ":" not in raw:
        raise ValueError(f"Invalid format: {line}")
    team_name, rest = raw.split(" - ", 1)
    username, password = rest.split(":", 1)
    team_name = team_name.strip()
    username = username.strip()
    password = password.strip()
    if not team_name or not username or not password:
        raise ValueError(f"Invalid format (empty field): {line}")
    return team_name, username, password


def ensure_schema(conn: sqlite3.Connection):
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import accounts from lines: <team name> - <username>:<password>"
    )
    parser.add_argument("--file", required=True, help="Path to credentials text file")
    args = parser.parse_args()

    load_dotenv()
    db_path = os.getenv("DB_PATH", "./data/print_jobs.db")

    with open(args.file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    records = []
    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = parse_line(stripped)
            if parsed:
                records.append(parsed)
        except ValueError as exc:
            raise ValueError(f"Line {idx}: {exc}") from exc

    conn = sqlite3.connect(db_path)
    try:
        ensure_schema(conn)
        now = utc_now_iso()
        for team_name, username, password in records:
            conn.execute(
                """
                INSERT INTO users (username, team_name, password_hash, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    team_name = excluded.team_name,
                    password_hash = excluded.password_hash
                """,
                (username, team_name, generate_password_hash(password), now),
            )
        conn.commit()
    finally:
        conn.close()

    print(f"Imported {len(records)} account(s).")


if __name__ == "__main__":
    main()
