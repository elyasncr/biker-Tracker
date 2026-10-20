"""A aba Treinador. O router monta os insumos e compoe; a leitura mora no
services/coach.py, que nao conhece banco nem HTTP."""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Activity, CoachGoal, WeightEntry
from ..services import coach as coach_service
from ..services import insight as insight_service
from ..services import metrics

router = APIRouter(prefix="/api/coach", tags=["treinador"])

RECENT_WEEKS = 4
FTP_DEFAULT = 220


class GoalInput(BaseModel):
    rides_per_week: int
    minutes_per_week: int
    target_weight_kg: float | None = None

    @field_validator("rides_per_week")
    @classmethod
    def _pelo_menos_um(cls, v):
        if not 1 <= v <= 14:
            raise ValueError("Entre 1 e 14 pedais por semana")
        return v

    @field_validator("minutes_per_week")
    @classmethod
    def _minutos_plausiveis(cls, v):
        if not 30 <= v <= 3000:
            raise ValueError("Entre 30 e 3000 minutos por semana")
        return v


def _get_goal(db: Session) -> CoachGoal:
    """Linha unica, criada na primeira leitura."""
    goal = db.get(CoachGoal, 1)
    if goal is None:
        goal = CoachGoal(id=1)
        db.add(goal)
        db.commit()
        db.refresh(goal)
    return goal


def _goal_dict(goal: CoachGoal) -> dict:
    return {
        "rides_per_week": goal.rides_per_week,
        "minutes_per_week": goal.minutes_per_week,
        "target_weight_kg": goal.target_weight_kg,
    }


def _rides(db: Session) -> list[dict]:
    """Treinos no formato simples que o services/coach.py espera."""
    return [
        {"date": a.started_at.date(), "minutes": a.moving_time_s / 60, "load": a.tss or 0.0}
        for a in db.scalars(select(Activity).order_by(Activity.started_at))
    ]


def _pmc(rides: list[dict], hoje: date) -> list[dict]:
    diario: dict[date, float] = {}
    for r in rides:
        diario[r["date"]] = diario.get(r["date"], 0.0) + r["load"]
    if not diario:
        return []
    return metrics.performance_management(diario, min(diario), hoje)


def _week(rides: list[dict], hoje: date) -> dict:
    inicio = hoje - timedelta(days=hoje.weekday())
    da_semana = [r for r in rides if r["date"] >= inicio]
    return {
        "rides_done": len(da_semana),
        "minutes_done": sum(r["minutes"] for r in da_semana),
    }


def _recent(rides: list[dict], hoje: date) -> dict:
    corte = hoje - timedelta(weeks=RECENT_WEEKS)
    recentes = [r for r in rides if r["date"] >= corte]
    if not recentes:
        # Sem historico recente, o teto vira o piso: nao sugerir pedal longo a
        # quem nao pedalou nas ultimas semanas.
        return {"longest_ride_min": 40.0, "avg_ride_min": 40.0, "weeks_avg_minutes": 0.0}
    minutos = [r["minutes"] for r in recentes]
    return {
        "longest_ride_min": max(minutos),
        "avg_ride_min": sum(minutos) / len(minutos),
        "weeks_avg_minutes": sum(minutos) / RECENT_WEEKS,
    }


def _weeks_history(rides: list[dict], goal: dict, hoje: date) -> list[dict]:
    prog = coach_service.progress(rides, [], goal, hoje)
    return [
        {"minutes": w["minutes"], "rides": w["rides"], "met_goal": w["met_goal"]}
        for w in prog["consistency"]["weeks"]
    ]


@router.get("")
def coach_reading(db: Session = Depends(get_db)):
    """As tres leituras num payload so."""
    hoje = date.today()
    goal = _goal_dict(_get_goal(db))
    rides = _rides(db)
    pesos = [
        {"date": e.measured_on, "weight_kg": e.weight_kg}
        for e in db.scalars(select(WeightEntry).order_by(WeightEntry.measured_on))
    ]

    pmc = _pmc(rides, hoje)
    prontidao = coach_service.readiness(rides, pmc, hoje)
    prescricao = coach_service.prescription(prontidao, goal, _week(rides, hoje), _recent(rides, hoje))
    progresso = coach_service.progress(rides, pesos, goal, hoje)
    sugestao = coach_service.suggest_goal(goal, _weeks_history(rides, goal, hoje))

    # Quarta linha do progresso (spec 6.3). Fica no router e nao no coach.py
    # porque CTL vem do metrics, e o modulo puro nao conhece esse mundo. Vai
    # rotulada: ela depende do FTP, que e o default de 220 W que ninguem mediu.
    progresso["fitness"] = {
        "ctl": pmc[-1]["ctl"] if pmc else 0.0,
        "series": [{"date": p["date"], "ctl": p["ctl"]} for p in pmc[-56:]],
        "depends_on_estimated_ftp": True,
    }

    return {
        "readiness": prontidao,
        "prescription": prescricao,
        "progress": progresso,
        "goal": goal,
        "goal_suggestion": sugestao,
        "ftp_is_default": get_settings().ftp_watts == FTP_DEFAULT,
    }


# Cache em processo: a geracao no Ollama leva dezenas de segundos, e o insight
# so muda quando o conjunto de treinos muda. Chave = (modelo, ids, ftp).
_insight_cache: dict[tuple, dict] = {}

INSIGHT_WINDOW_DAYS = 42
INSIGHT_FALLBACK_RIDES = 6


def _recent_activities(db: Session) -> list[Activity]:
    todos = list(db.scalars(select(Activity).order_by(Activity.started_at.desc())))
    corte = date.today() - timedelta(days=INSIGHT_WINDOW_DAYS)
    recentes = [a for a in todos if a.started_at.date() >= corte]
    if len(recentes) < 2:
        recentes = todos[:INSIGHT_FALLBACK_RIDES]
    return list(reversed(recentes))  # ordem cronologica


@router.get("/insight")
def coach_insight(refresh: bool = False, db: Session = Depends(get_db)):
    """Analise acionavel dos treinos recentes: numeros (para os graficos) +
    comentario do Ollama (best-effort). Cacheia por conjunto de treinos."""
    settings = get_settings()
    recentes = _recent_activities(db)
    if not recentes:
        return {"available": False, "reason": "Sem treinos para analisar ainda."}

    rides = [
        {
            "date": a.started_at.date(),
            "title": a.title,
            "minutes": a.moving_time_s / 60,
            "distance_km": a.distance_km,
            "np": a.normalized_power,
            "tss": a.tss,
            "vi": a.variability_index,
            "avg_cadence": a.avg_cadence,
            "power_is_estimated": a.power_is_estimated,
            "payload": a.stream.payload if a.stream else None,
        }
        for a in recentes
    ]
    summary = insight_service.build_summary(rides, settings.ftp_watts)

    key = (settings.ollama_model, tuple(a.id for a in recentes), settings.ftp_watts)
    cached = _insight_cache.get(key)
    if refresh:
        cached = None

    if cached is None and settings.ollama_enabled:
        texto = insight_service.generate_text(summary, settings.ollama_host, settings.ollama_model)
        if texto:
            cached = {"text": texto, "generated_at": datetime.utcnow().isoformat()}
            _insight_cache[key] = cached

    return {
        "available": True,
        "summary": summary,
        "text": cached["text"] if cached else None,
        "text_available": cached is not None,
        "model": settings.ollama_model,
        "generated_at": cached["generated_at"] if cached else None,
    }


_guide_cache: dict[tuple, dict] = {}


@router.get("/evolution")
def coach_evolution(refresh: bool = False, db: Session = Depends(get_db)):
    """Tela "Técnica" / Pontos de evolução: os mesmos números/gráficos do insight,
    com um guia detalhado em 3 partes por dimensão (o que mostra, como melhorar,
    como aplicar no treino)."""
    settings = get_settings()
    recentes = _recent_activities(db)
    if not recentes:
        return {"available": False, "reason": "Sem treinos para analisar ainda."}

    rides = [
        {
            "date": a.started_at.date(),
            "title": a.title,
            "minutes": a.moving_time_s / 60,
            "distance_km": a.distance_km,
            "np": a.normalized_power,
            "tss": a.tss,
            "vi": a.variability_index,
            "avg_cadence": a.avg_cadence,
            "power_is_estimated": a.power_is_estimated,
            "payload": a.stream.payload if a.stream else None,
        }
        for a in recentes
    ]
    summary = insight_service.build_summary(rides, settings.ftp_watts)

    key = (settings.ollama_model, tuple(a.id for a in recentes), settings.ftp_watts)
    cached = None if refresh else _guide_cache.get(key)
    if cached is None and settings.ollama_enabled:
        guia = insight_service.generate_guide(summary, settings.ollama_host, settings.ollama_model)
        if guia:
            cached = {"guide": guia, "generated_at": datetime.utcnow().isoformat()}
            _guide_cache[key] = cached

    return {
        "available": True,
        "summary": summary,
        "guide": cached["guide"] if cached else None,
        "guide_available": cached is not None,
        "model": settings.ollama_model,
        "generated_at": cached["generated_at"] if cached else None,
    }


@router.get("/goal")
def get_goal(db: Session = Depends(get_db)):
    return _goal_dict(_get_goal(db))


@router.put("/goal")
def set_goal(payload: GoalInput, db: Session = Depends(get_db)):
    goal = _get_goal(db)
    goal.rides_per_week = payload.rides_per_week
    goal.minutes_per_week = payload.minutes_per_week
    goal.target_weight_kg = payload.target_weight_kg
    goal.updated_at = datetime.utcnow()
    db.commit()
    return _goal_dict(goal)
