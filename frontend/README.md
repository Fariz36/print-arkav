# Frontend (React)

Login + upload UI for the print service.

## Run (dev)
```bash
cd frontend
npm install
npm run dev
```

By default, Vite proxies `/api` to `http://127.0.0.1:3000`.
If backend is different, run:
```bash
VITE_BACKEND_URL=http://<backend-host>:3000 npm run dev
```

## Build
```bash
npm run build
```

Then serve `frontend/dist` with Nginx or any static server.
