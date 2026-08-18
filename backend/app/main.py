from fastapi import FastAPI

app = FastAPI(title="MaestroBank API")


@app.get("/")
def read_root():
    return {"message": "MaestroBank API is running"}


@app.get("/health")
def health_check():
    return {"status": "ok"}
