import shutil
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import SyncLog
from ..schemas import SyncResult
from ..services import igpsport_client
from ..services.ingest import import_file, sync_folder

router = APIRouter(prefix="/api", tags=["sync"])


@router.post("/sync", response_model=SyncResult)
def sync(force: bool = False, db: Session = Depends(get_db)):
    """Le a pasta data/ e importa todo .fit que ainda nao esta no banco."""
    return sync_folder(db, force=force)


@router.get("/sync/history")
def sync_history(db: Session = Depends(get_db), limit: int = 20):
    logs = db.scalars(select(SyncLog).order_by(desc(SyncLog.ran_at)).limit(limit))
    return [
        {
            "ran_at": log.ran_at,
            "source": log.source,
            "imported": log.imported,
            "skipped": log.skipped,
            "failed": log.failed,
            "detail": log.detail,
        }
        for log in logs
    ]


@router.post("/upload")
async def upload_fit(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Sobe um .fit direto pela interface. Ele e salvo em data/ e importado na hora."""
    if not file.filename or not file.filename.lower().endswith(".fit"):
        raise HTTPException(400, "Envie um arquivo .fit")

    settings = get_settings()
    destination = settings.data_path / file.filename
    with destination.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    try:
        activity = import_file(db, destination)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(422, f"Nao consegui ler o arquivo: {exc}") from exc

    if activity is None:
        return {"status": "duplicado", "message": "Esse treino ja estava importado."}
    return {"status": "importado", "activity_id": activity.id}


# --------------------------------------------------------------------------
# iGPSPORT Open Platform - so responde se voce tiver credenciais aprovadas
# --------------------------------------------------------------------------


@router.get("/igpsport/status")
def igpsport_status():
    settings = get_settings()
    return {
        "enabled": settings.igpsport_enabled,
        "configured": bool(settings.igpsport_client_id and settings.igpsport_token_url),
        "how_to_apply": "Envie os dados do app para global@igpsport.com "
        "(nome, logo 120x120, descricao, redirect_url, callback_url, razao social, site).",
        "docs": "https://www.igpsport.com/support/app/openapi",
    }


@router.get("/igpsport/authorize")
def igpsport_authorize():
    try:
        return {"url": igpsport_client.authorize_url()}
    except igpsport_client.IgpsportNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/igpsport/callback")
async def igpsport_callback(code: str, db: Session = Depends(get_db)):
    try:
        await igpsport_client.exchange_code(db, code)
    except igpsport_client.IgpsportNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"status": "autorizado"}


@router.post("/igpsport/sync")
async def igpsport_sync(since: datetime | None = None, db: Session = Depends(get_db)):
    """Baixa os .fit novos da conta iGPSPORT para data/ e importa."""
    settings = get_settings()
    try:
        activities = await igpsport_client.fetch_activities(db, since)
    except igpsport_client.IgpsportNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc

    downloaded = 0
    for item in activities:
        activity_id = str(item.get("id") or item.get("rideId") or "")
        if not activity_id:
            continue
        destination = settings.data_path / f"igpsport-{activity_id}.fit"
        if destination.exists():
            continue
        await igpsport_client.download_fit(db, activity_id, destination)
        downloaded += 1

    result = sync_folder(db)
    result["downloaded_from_api"] = downloaded
    return result
