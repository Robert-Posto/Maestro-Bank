"""future-service-1 — placeholder rezervat pentru o funcționalitate viitoare.

Nu are încă responsabilități definite și nu se conectează la nicio bază de
date. Când va primi o funcționalitate reală, baza rezervată pentru el în
MongoDB este `future1_db` (vezi docker-compose.yml / .env.example).
"""

from fastapi import FastAPI

app = FastAPI(title="MaestroBank Future Service 1")


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "future-service-1"}
