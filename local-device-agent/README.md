# Local Device Agent

Runs on your home/office PC (same Wi-Fi/LAN as printer). It pulls jobs from Azure VM and prints via CUPS `lp`.

## Quick start
```bash
cd local-device-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env: SERVER_BASE_URL, AGENT_TOKEN, PRINTER_NAME
python agent.py
```

## Printer check
```bash
lpstat -p
lp -d hp_m255nw /tmp/test.txt
```

## Run as systemd service (Linux)
1. Copy folder to `/opt/local-device-agent`
2. Ensure `.venv` exists there and dependencies installed
3. Edit `print-agent.service` (username/path if needed)
4. Install service:
```bash
sudo cp print-agent.service /etc/systemd/system/print-agent.service
sudo systemctl daemon-reload
sudo systemctl enable --now print-agent
sudo systemctl status print-agent
```

## Behavior
- Polls VM every few seconds
- Downloads one job at a time
- Renders source file to PDF on local device with hardcoded style, then prints via `lp -d <PRINTER_NAME>`
- Reports `done`/`failed` to server
- Always deletes local temp file after each attempt

## Hardcoded print style
The agent enforces fixed styling locally (users cannot change it):
- Font: `Courier`
- Font size: `10`
- Margins and line spacing are fixed in `agent.py`
