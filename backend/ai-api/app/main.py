from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import analysis

app = FastAPI(title="AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite 개발 서버
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis.router)


@app.get("/health")
def health():
    return {"status": "ok"}
