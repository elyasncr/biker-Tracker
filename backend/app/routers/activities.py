from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Activity, Bike
from ..schemas import ActivityDetail, ActivitySummary

router = APIRouter(prefix="/api/activities", tags=["activities"])


@router.get("", response_model=list[ActivitySummary])
def list_activities(
    db: Session = Depends(get_db),
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    bike_id: int | None = None,
):
    stmt = select(Activity).order_by(Activity.started_at.desc())
    if start:
        stmt = stmt.where(Activity.started_at >= start)
    if end:
        stmt = stmt.where(Activity.started_at <= end)
    if bike_id:
        stmt = stmt.where(Activity.bike_id == bike_id)

    result = []
    for ride in db.scalars(stmt.limit(limit).offset(offset)):
        payload = ActivitySummary.model_validate(ride)
        payload.bike_name = ride.bike.name if ride.bike else None
        result.append(payload)
    return result


@router.get("/{activity_id}", response_model=ActivityDetail)
def get_activity(activity_id: int, db: Session = Depends(get_db), streams: bool = True):
    activity = db.get(Activity, activity_id)
    if activity is None:
        raise HTTPException(404, "Treino não encontrado")
    payload = ActivityDetail.model_validate(activity)
    payload.bike_name = activity.bike.name if activity.bike else None
    if streams and activity.stream is not None:
        payload.streams = activity.stream.payload
    return payload


@router.patch("/{activity_id}", response_model=ActivitySummary)
def update_activity(
    activity_id: int,
    title: str | None = None,
    notes: str | None = None,
    bike_id: int | None = None,
    db: Session = Depends(get_db),
):
    activity = db.get(Activity, activity_id)
    if activity is None:
        raise HTTPException(404, "Treino não encontrado")
    if title is not None:
        activity.title = title
    if notes is not None:
        activity.notes = notes
    if bike_id is not None:
        # bike_id = 0 desatribui: e o unico jeito de dizer "nenhuma" por query string,
        # onde ausente e None e ja significa "nao mexe".
        if bike_id == 0:
            activity.bike_id = None
        else:
            if db.get(Bike, bike_id) is None:
                raise HTTPException(404, "Bike não encontrada")
            activity.bike_id = bike_id
    db.commit()
    db.refresh(activity)
    payload = ActivitySummary.model_validate(activity)
    payload.bike_name = activity.bike.name if activity.bike else None
    return payload


@router.delete("/{activity_id}", status_code=204)
def delete_activity(activity_id: int, db: Session = Depends(get_db)):
    activity = db.get(Activity, activity_id)
    if activity is None:
        raise HTTPException(404, "Treino não encontrado")
    db.delete(activity)
    db.commit()
