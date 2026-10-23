from fastapi import FastAPI

app = FastAPI(title="AI Support Platform")


@app.get("/health")
def health_check():
    return {"status": "ok"}