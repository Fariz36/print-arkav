import os
import subprocess
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from dotenv import load_dotenv

load_dotenv()

SERVER_BASE_URL = os.getenv("SERVER_BASE_URL", "http://127.0.0.1:3000").rstrip("/")
AGENT_TOKEN = os.getenv("AGENT_TOKEN", "")
AGENT_ID = os.getenv("AGENT_ID", "default-agent")
PRINTER_NAME = os.getenv("PRINTER_NAME", "hp_m255nw")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "3"))
WORK_DIR = os.getenv("WORK_DIR", "./spool")

if not AGENT_TOKEN:
    raise RuntimeError("AGENT_TOKEN is required")

Path(WORK_DIR).mkdir(parents=True, exist_ok=True)

HEADERS = {"Authorization": f"Bearer {AGENT_TOKEN}"}


def api_get(path: str, **kwargs):
    url = urljoin(f"{SERVER_BASE_URL}/", path.lstrip("/"))
    return requests.get(url, headers=HEADERS, timeout=30, **kwargs)


def api_post(path: str, **kwargs):
    url = urljoin(f"{SERVER_BASE_URL}/", path.lstrip("/"))
    return requests.post(url, headers=HEADERS, timeout=30, **kwargs)


def print_file(local_path: Path):
    cmd = ["lp", "-d", PRINTER_NAME, str(local_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        raise RuntimeError(f"lp failed (code={result.returncode}): {stderr or stdout}")


def loop_once():
    res = api_get(f"/api/agent/jobs/next?agent_id={AGENT_ID}")
    res.raise_for_status()
    payload = res.json()
    job = payload.get("job")

    if not job:
        return False

    job_id = job["id"]
    filename = job.get("filename", f"job-{job_id}")
    download_url = job["download_url"]

    local_path = Path(WORK_DIR) / f"{job_id}_{os.path.basename(filename)}"

    try:
        dl = api_get(download_url, stream=True)
        dl.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in dl.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        print_file(local_path)
        done = api_post(f"/api/agent/jobs/{job_id}/done")
        done.raise_for_status()
        print(f"[DONE] job={job_id} file={filename}")
    except Exception as exc:
        try:
            api_post(f"/api/agent/jobs/{job_id}/failed", json={"reason": str(exc)[:500]})
        except Exception:
            pass
        print(f"[FAIL] job={job_id} file={filename} err={exc}")
    finally:
        if local_path.exists():
            local_path.unlink()

    return True


def main():
    print(
        f"Agent started: base_url={SERVER_BASE_URL} agent_id={AGENT_ID} printer={PRINTER_NAME}"
    )
    while True:
        try:
            got_job = loop_once()
            if not got_job:
                time.sleep(POLL_INTERVAL_SECONDS)
        except requests.RequestException as exc:
            print(f"[NET] {exc}")
            time.sleep(POLL_INTERVAL_SECONDS)
        except Exception as exc:
            print(f"[ERR] {exc}")
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
