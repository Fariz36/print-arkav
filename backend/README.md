# Azure VM Service

Print-job API for your Azure VM (Option 1: local PC agent polls jobs).

## Features
- User login (`username/password`)
- Upload `.cpp`, `.c`, `.py`, `.java` after login
- Queue jobs in SQLite with `requested_by` (team name)
- Agent endpoints to claim/download/mark done
- Deletes uploaded file from VM when job marked done

## Quick start
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and set AGENT_TOKEN + APP_SECRET
python app.py
```

Default API listens on `0.0.0.0:3000`.

## Auth flow
1. `POST /api/auth/login` with JSON:
```json
{ "username": "admin", "password": "admin123" }
```
2. Use returned bearer token in `Authorization` header for:
- `POST /api/upload`
- `GET /api/jobs`
- `GET /api/auth/me`

## Add or update an account
```bash
cd backend
source .venv/bin/activate
python create_user.py --team-name "Team Alpha" --username alice --password 'StrongPass123!'
```

You can also seed users via `.env`:
```env
DEFAULT_USERS=admin:admin123,alice:alice123
```

## Bulk import team credentials
Prepare a text file with this format per line:
```text
<team name> - <username>:<password>
```

Then import:
```bash
cd backend
source .venv/bin/activate
python import_team_credentials.py --file ./team_credentials.txt
```

## Endpoints
- `GET /health`
- `POST /api/auth/login`
- `GET /api/auth/me` (Bearer)
- `POST /api/upload` (Bearer + multipart form: `file`)
- `GET /api/jobs` (Bearer, own jobs only)
- `GET /api/agent/jobs/next?agent_id=my-pc` (Agent Bearer token)
- `GET /api/agent/jobs/{id}/download` (Agent Bearer token)
- `POST /api/agent/jobs/{id}/done` (Agent Bearer token)
- `POST /api/agent/jobs/{id}/failed` (Agent Bearer token + optional JSON `{ "reason": "..." }`)

## Curl test
```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:3000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' | jq -r .access_token)

curl -X POST http://127.0.0.1:3000/api/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/test.cpp"
```

## Azure VM networking
- Keep inbound NSG open for app port(s), e.g. `3000`
- Domain `print.cp.arkav.com` can reverse proxy to this app
- No inbound route to home PC is needed
