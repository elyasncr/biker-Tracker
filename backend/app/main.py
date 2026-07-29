import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import Base, SessionLocal, engine
from .routers import activities, analysis, bikes, coach, stats, sync, weight
from .services.ingest import sync_folder

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("igpsport")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    settings = get_settings()
    log.info("Lendo treinos de %s", settings.data_path)
    with SessionLocal() as db:
        result = sync_folder(db)
    log.info("Importados %s, ja existentes %s, falhas %s", result["imported"], result["skipped"], result["failed"])
    yield


app = FastAPI(
    title="Bike Tracker",
    description="Acompanhamento de evolucao nos treinos de bike a partir de arquivos .fit do iGPSPORT.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(activities.router)
app.include_router(analysis.router)
app.include_router(bikes.router)
app.include_router(stats.router)
app.include_router(sync.router)
app.include_router(coach.router)
app.include_router(weight.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
