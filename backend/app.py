import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from flask import Flask, abort, g, jsonify, request, send_file
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "3000"))
DB_PATH = os.getenv("DB_PATH", "./data/print_jobs.db")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./data/uploads")
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
AGENT_TOKEN = os.getenv("AGENT_TOKEN", "")
APP_SECRET = os.getenv("APP_SECRET", "change-this-secret")
ACCESS_TOKEN_TTL_SECONDS = int(os.getenv("ACCESS_TOKEN_TTL_SECONDS", str(12 * 60 * 60)))
DEFAULT_USERS = os.getenv("DEFAULT_USERS", "admin:admin123")

ALLOWED_EXTENSIONS = {".cpp", ".py", ".c", ".java", ".pdf"}

app = Flask(__name__)
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
token_serializer = URLSafeTimedSerializer(APP_SECRET)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def tx_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with tx_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_name TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                ext TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                requested_by TEXT,
                assigned_agent_id TEXT,
                fail_reason TEXT
            )
            """
        )
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

        # Backward-compatible migration for older DBs without requested_by.
        cols = conn.execute("PRAGMA table_info(jobs)").fetchall()
        col_names = {c["name"] for c in cols}
        if "requested_by" not in col_names:
            conn.execute("ALTER TABLE jobs ADD COLUMN requested_by TEXT")
        user_cols = conn.execute("PRAGMA table_info(users)").fetchall()
        user_col_names = {c["name"] for c in user_cols}
        if "team_name" not in user_col_names:
            conn.execute("ALTER TABLE users ADD COLUMN team_name TEXT")
            conn.execute("UPDATE users SET team_name = username WHERE team_name IS NULL OR team_name = ''")

        ensure_default_users(conn)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def teardown_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def require_agent_auth() -> None:
    if not AGENT_TOKEN:
        abort(500, description="Server misconfiguration: AGENT_TOKEN is empty")

    auth_header = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if not auth_header.startswith(prefix):
        abort(401, description="Missing bearer token")

    token = auth_header[len(prefix) :]
    if token != AGENT_TOKEN:
        abort(401, description="Invalid bearer token")


def ensure_default_users(conn: sqlite3.Connection) -> None:
    now = utc_now_iso()
    for pair in DEFAULT_USERS.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        username, password = pair.split(":", 1)
        username = username.strip()
        password = password.strip()
        if not username or not password:
            continue

        exists = conn.execute(
            "SELECT id FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if exists is None:
            conn.execute(
                "INSERT INTO users (username, team_name, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (username, username, generate_password_hash(password), now),
            )


def issue_access_token(username: str) -> str:
    return token_serializer.dumps({"username": username}, salt="access-token")


def verify_access_token(token: str) -> str:
    try:
        payload = token_serializer.loads(
            token,
            salt="access-token",
            max_age=ACCESS_TOKEN_TTL_SECONDS,
        )
    except SignatureExpired:
        abort(401, description="Token expired")
    except BadSignature:
        abort(401, description="Invalid token")

    username = payload.get("username")
    if not username:
        abort(401, description="Invalid token payload")
    return username


def require_user_auth() -> str:
    auth_header = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if not auth_header.startswith(prefix):
        abort(401, description="Missing bearer token")

    token = auth_header[len(prefix) :]
    return verify_access_token(token)


def sanitize_name(name: str) -> str:
    base = os.path.basename(name)
    return base.replace("\x00", "")


@app.get("/health")
def health():
    return jsonify({"ok": True, "time": utc_now_iso()})


@app.post("/api/auth/login")
def login():
    if not request.is_json:
        abort(400, description="JSON body is required")

    body = request.get_json(silent=True) or {}
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    if not username or not password:
        abort(400, description="username and password are required")

    db = get_db()
    row = db.execute(
        "SELECT username, password_hash FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if row is None or not check_password_hash(row["password_hash"], password):
        abort(401, description="Invalid credentials")

    token = issue_access_token(username)
    return jsonify(
        {
            "ok": True,
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": ACCESS_TOKEN_TTL_SECONDS,
            "username": username,
        }
    )


@app.get("/api/auth/me")
def me():
    username = require_user_auth()
    db = get_db()
    row = db.execute("SELECT team_name FROM users WHERE username = ?", (username,)).fetchone()
    team_name = row["team_name"] if row else username
    return jsonify({"ok": True, "username": username, "team_name": team_name})


@app.post("/api/upload")
def upload_job():
    username = require_user_auth()
    db = get_db()
    user_row = db.execute(
        "SELECT team_name FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    team_name = user_row["team_name"] if user_row and user_row["team_name"] else username

    if "file" not in request.files:
        abort(400, description="'file' is required")

    file = request.files["file"]
    if not file or not file.filename:
        abort(400, description="filename is empty")

    safe_name = sanitize_name(file.filename)
    ext = Path(safe_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        abort(400, description=f"File extension not allowed: {ext}")

    payload = file.read()
    if len(payload) > MAX_UPLOAD_BYTES:
        abort(413, description="File too large")

    now = utc_now_iso()
    stored_name = f"{int(datetime.now().timestamp() * 1000)}_{safe_name}"
    file_path = str(Path(UPLOAD_DIR) / stored_name)

    with open(file_path, "wb") as f:
        f.write(payload)

    cur = db.execute(
        """
        INSERT INTO jobs (
            original_name, stored_name, file_path, ext, status, created_at, updated_at, requested_by
        ) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
        """,
        (safe_name, stored_name, file_path, ext, now, now, team_name),
    )
    db.commit()

    return jsonify(
        {
            "ok": True,
            "job_id": cur.lastrowid,
            "filename": safe_name,
            "status": "pending",
            "requested_by": team_name,
        }
    ), 201


@app.get("/api/agent/jobs/next")
def agent_next_job():
    require_agent_auth()

    agent_id = request.args.get("agent_id", "default-agent").strip() or "default-agent"
    db = get_db()

    db.execute("BEGIN IMMEDIATE")
    row = db.execute(
        "SELECT * FROM jobs WHERE status = 'pending' ORDER BY id ASC LIMIT 1"
    ).fetchone()

    if row is None:
        db.commit()
        return jsonify({"ok": True, "job": None})

    db.execute(
        """
        UPDATE jobs
        SET status = 'processing', assigned_agent_id = ?, updated_at = ?
        WHERE id = ?
        """,
        (agent_id, utc_now_iso(), row["id"]),
    )
    db.commit()

    return jsonify(
        {
            "ok": True,
            "job": {
                "id": row["id"],
                "filename": row["original_name"],
                "ext": row["ext"],
                "requested_by": row["requested_by"],
                "download_url": f"/api/agent/jobs/{row['id']}/download",
            },
        }
    )


@app.get("/api/agent/jobs/<int:job_id>/download")
def agent_download_job(job_id: int):
    require_agent_auth()

    db = get_db()
    row = db.execute(
        "SELECT id, status, file_path FROM jobs WHERE id = ?",
        (job_id,),
    ).fetchone()

    if row is None:
        abort(404, description="Job not found")

    if row["status"] not in {"processing", "pending"}:
        abort(409, description="Job is not downloadable")

    file_path = row["file_path"]
    if not os.path.exists(file_path):
        abort(410, description="Job file missing")

    return send_file(file_path, as_attachment=True)


@app.post("/api/agent/jobs/<int:job_id>/done")
def agent_done_job(job_id: int):
    require_agent_auth()

    db = get_db()
    row = db.execute("SELECT id, file_path, status FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        abort(404, description="Job not found")

    if row["status"] not in {"processing", "pending"}:
        return jsonify({"ok": True, "status": row["status"]})

    db.execute(
        "UPDATE jobs SET status = 'done', updated_at = ? WHERE id = ?",
        (utc_now_iso(), job_id),
    )
    db.commit()

    file_path = row["file_path"]
    if file_path and os.path.exists(file_path):
        os.remove(file_path)

    return jsonify({"ok": True, "status": "done"})


@app.post("/api/agent/jobs/<int:job_id>/failed")
def agent_failed_job(job_id: int):
    require_agent_auth()

    reason: Optional[str] = None
    if request.is_json:
        body = request.get_json(silent=True) or {}
        reason = str(body.get("reason", ""))[:500]

    db = get_db()
    row = db.execute("SELECT id, status FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        abort(404, description="Job not found")

    if row["status"] == "done":
        return jsonify({"ok": True, "status": "done"})

    db.execute(
        "UPDATE jobs SET status = 'failed', fail_reason = ?, updated_at = ? WHERE id = ?",
        (reason, utc_now_iso(), job_id),
    )
    db.commit()

    return jsonify({"ok": True, "status": "failed"})


@app.get("/api/jobs")
def list_jobs():
    username = require_user_auth()
    db = get_db()
    user_row = db.execute(
        "SELECT team_name FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    team_name = user_row["team_name"] if user_row and user_row["team_name"] else username
    rows = db.execute(
        """
        SELECT id, original_name, ext, status, requested_by, assigned_agent_id, created_at, updated_at, fail_reason
        FROM jobs
        WHERE requested_by = ?
        ORDER BY id DESC
        LIMIT 100
        """,
        (team_name,),
    ).fetchall()

    items = [dict(r) for r in rows]
    return jsonify({"ok": True, "jobs": items})


if __name__ == "__main__":
    init_db()
    app.run(host=HOST, port=PORT)
