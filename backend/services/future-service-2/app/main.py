"""future-service-2 — placeholder rezervat pentru o funcționalitate viitoare.

Nu are încă responsabilități definite și nu se conectează la nicio bază de
date. Când va primi o funcționalitate reală, baza rezervată pentru el în
MongoDB este `future2_db` (vezi docker-compose.yml / .env.example).
"""

from fastapi import FastAPI

app = FastAPI(title="MaestroBank Future Service 2")


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "future-service-2"}
