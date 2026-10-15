from fastapi import FastAPI

app = FastAPI(title="Ouve.AI")

@app.get("/health")
def health():
    return {"status": "ok"}