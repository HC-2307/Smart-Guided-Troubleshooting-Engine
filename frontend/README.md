# Frontend (M4)

Plain HTML/CSS/JS — no build step, matches the "lightweight frontend" scope in the playbook.

## Files

- `index.html` — page shell (input + results container + dev panel)
- `style.css` — all styling
- `app.js` — fetch call to the backend, rendering logic, OPEN button handling
- `config.js` — API base URL, edit this if the backend runs on a different host/port

## Running it

1. Make sure the backend is running (from repo root):
   ```
   uvicorn backend.main:app --reload
   ```
   This serves on `http://localhost:8000`, with the troubleshoot route at `/v1/troubleshoot`
   (see `backend/main.py` — router is mounted with `prefix="/v1"`).

2. Serve this folder with any static server, e.g.:
   ```
   cd frontend
   python3 -m http.server 5500
   ```
   Then open `http://localhost:5500`.

   (Opening `index.html` directly via `file://` usually also works for `fetch`, but some
   browsers block it — a static server avoids that entirely.)

3. If you get a CORS error in the console, the backend needs CORS enabled. Ask M3 to add
   this to `backend/main.py` (safe for local dev):
   ```python
   from fastapi.middleware.cors import CORSMiddleware

   app.add_middleware(
       CORSMiddleware,
       allow_origins=["*"],
       allow_methods=["*"],
       allow_headers=["*"],
   )
   ```

## Known limitation: OPEN button

Deeplinks returned by the API are `bixby://...` URIs — they only resolve on an actual
Galaxy device. Clicking OPEN in this browser demo shows what the deeplink *would* do
(via an alert) rather than pretending to navigate somewhere. That's expected, not a bug.

## Dev panel

Small gear icon, bottom-right. Shows last query's status/latency and the raw JSON response —
useful for the demo (section 9.2/9.4 in the playbook mention showing cache hit/latency).

## Not done yet (intentionally — baseline first)

- Evaluation harness (section 9.3) — separate script, not part of this UI
- Any visual polish / innovation-layer UI — comes after this works end-to-end against the real API
