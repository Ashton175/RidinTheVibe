from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.auth import router as auth_router
from app.api.uploads import router as uploads_router
from app.api.risk_analysis import router as risk_analysis_router
from app.api.schedule import router as schedule_router

app = FastAPI(title=settings.app_name)
app.include_router(auth_router)
app.include_router(uploads_router)
app.include_router(risk_analysis_router)
app.include_router(schedule_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
