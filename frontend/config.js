// Point this at wherever backend/main.py is running.
// FastAPI default when M3 runs `uvicorn backend.main:app --reload` is port 8000,
// and the router is mounted under the /v1 prefix (see backend/main.py).
const CONFIG = {
  API_BASE_URL: "http://localhost:8000/v1",
  TROUBLESHOOT_ENDPOINT: "/troubleshoot",
};
