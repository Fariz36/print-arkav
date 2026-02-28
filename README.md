# Internet-to-Local Printer Bridge

This repository contains 3 components:

- `azure-vm-service/`: deploy on Azure VM (auth + upload API + queue)
- `local-device-agent/`: run on your local PC (poll + print + delete)
- `frontend/`: React UI (login + file upload)

Architecture (Option 1): local agent **pulls** jobs from Azure VM, so Azure never needs direct inbound access to your home PC.
