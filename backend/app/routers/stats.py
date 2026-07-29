from collections import defaultdict
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Activity
from ..schemas import PmcPoint, Totals, TrendPoint
from ..services import metrics

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _window(db: Session, days: int | None):
    stmt = select(Activity).order_by(Activity.started_at)
    if days:
        stmt = stmt.where(Activity.started_at >= datetime.utcnow() - timedelta(days=days))
    return list(db.scalars(stmt))


@router.get("/totals", response_model=Totals)
def totals(days: int | None = Query(None, description="Janela em dias. Vazio = tudo."), db: Session = Depends(get_db)):
    rides = _window(db, days)
    distance = sum(a.distance_km for a in rides)
    moving = sum(a.moving_time_s for a in rides)
    return Totals(
        activities=len(rides),
        distance_km=round(distance, 1),
        moving_time_h=round(moving / 3600, 1),
        elevation_gain_m=round(sum(a.elevation_gain_m for a in rides), 0),
        tss=round(sum(a.tss or 0 for a in rides), 0),
        avg_speed_kmh=round(distance / (moving / 3600), 1) if moving else None,
        longest_ride_km=round(max((a.distance_km for a in rides), default=0), 1) or None,
        biggest_climb_m=round(max((a.elevation_gain_m for a in rides), default=0), 0) or None,
    )


@router.get("/trend", response_model=list[TrendPoint])
def trend(
    group_by: str = Query("week", pattern="^(week|month)$"),
    days: int | None = Query(365),
    db: Session = Depends(get_db),
):
    rides = _window(db, days)
    buckets: dict[str, list[Activity]] = defaultdict(list)
    for ride in rides:
        if group_by == "week":
            iso = ride.started_at.isocalendar()
            key = f"{iso.year}-S{iso.week:02d}"
        else:
            key = ride.started_at.strftime("%Y-%m")
        buckets[key].append(ride)

    points = []
    for key in sorted(buckets):
        group = buckets[key]
        distance = sum(a.distance_km for a in group)
        moving = sum(a.moving_time_s for a in group)
        powers = [a.avg_power for a in group if a.avg_power]
        points.append(
            TrendPoint(
                period=key,
                activities=len(group),
                distance_km=round(distance, 1),
                moving_time_h=round(moving / 3600, 2),
                elevation_gain_m=round(sum(a.elevation_gain_m for a in group), 0),
                tss=round(sum(a.tss or 0 for a in group), 0),
                avg_speed_kmh=round(distance / (moving / 3600), 1) if moving else None,
                avg_power=round(sum(powers) / len(powers), 0) if powers else None,
            )
        )
    return points


@router.get("/pmc", response_model=list[PmcPoint])
def pmc(days: int = Query(180), db: Session = Depends(get_db)):
    """Fitness (CTL), fadiga (ATL) e forma (TSB) dia a dia."""
    rides = list(db.scalars(select(Activity).order_by(Activity.started_at)))
    if not rides:
        return []
    daily: dict[date, float] = defaultdict(float)
    for ride in rides:
        daily[ride.started_at.date()] += ride.tss or 0

    end = date.today()
    start = min(daily) if daily else end
    series = metrics.performance_management(daily, start, end)
    cutoff = (end - timedelta(days=days)).isoformat()
    return [PmcPoint(**p) for p in series if p["date"] >= cutoff]


@router.get("/power-curve")
def power_curve(days: int | None = Query(None), db: Session = Depends(get_db)):
    """Melhor potencia de todos os treinos da janela, por duracao."""
    rides = _window(db, days)
    best: dict[str, dict] = {}
    for ride in rides:
        for seconds, watts in (ride.power_curve or {}).items():
            if seconds not in best or watts > best[seconds]["watts"]:
                best[seconds] = {
                    "watts": watts,
                    "activity_id": ride.id,
                    "date": ride.started_at.date().isoformat(),
                }
    return [
        {"seconds": int(s), **best[s]}
        for s in sorted(best, key=lambda x: int(x))
    ]


@router.get("/zones")
def zones(days: int | None = Query(90), db: Session = Depends(get_db)):
    rides = _window(db, days)
    hr_total: dict[str, float] = defaultdict(float)
    power_total: dict[str, float] = defaultdict(float)
    for ride in rides:
        for zone, seconds in (ride.hr_zones_s or {}).items():
            hr_total[zone] += seconds
        for zone, seconds in (ride.power_zones_s or {}).items():
            power_total[zone] += seconds
    return {
        "heart_rate": [{"zone": z, "seconds": round(s)} for z, s in sorted(hr_total.items())],
        "power": [{"zone": z, "seconds": round(s)} for z, s in sorted(power_total.items())],
    }


@router.get("/records")
def records(db: Session = Depends(get_db)):
    """Recordes pessoais simples, pra dar aquele gostinho de evolucao."""
    rides = list(db.scalars(select(Activity)))
    if not rides:
        return {}

    def best(attr, reverse=True):
        valid = [a for a in rides if getattr(a, attr) is not None]
        if not valid:
            return None
        winner = max(valid, key=lambda a: getattr(a, attr)) if reverse else min(valid, key=lambda a: getattr(a, attr))
        return {
            "value": getattr(winner, attr),
            "activity_id": winner.id,
            "date": winner.started_at.date().isoformat(),
        }

    return {
        "longest_distance_km": best("distance_km"),
        "longest_time_s": best("moving_time_s"),
        "biggest_climb_m": best("elevation_gain_m"),
        "fastest_avg_kmh": best("avg_speed_kmh"),
        "top_speed_kmh": best("max_speed_kmh"),
        "best_normalized_power": best("normalized_power"),
        "hardest_tss": best("tss"),
    }


@router.get("/settings")
def athlete_settings():
    settings = get_settings()
    return {
        "ftp_watts": settings.ftp_watts,
        "hr_max": settings.hr_max,
        "hr_rest": settings.hr_rest,
        "data_dir": str(settings.data_path),
        "igpsport_enabled": settings.igpsport_enabled,
    }
