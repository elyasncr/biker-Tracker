from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Activity
from ..services import analysis, drivetrain
from ..services import insight as insight_service

router = APIRouter(prefix="/api/activities", tags=["analise"])

# Cache das dicas localizadas (LLM, lento). Chave = (modelo, activity_id, ftp).
_route_advice_cache: dict[tuple, dict] = {}


@router.get("/{activity_id}/analysis")
def activity_analysis(activity_id: int, db: Session = Depends(get_db)):
    """Telemetria do pedal: melhor e pior trecho, com o motivo de cada um."""
    activity = db.get(Activity, activity_id)
    if activity is None:
        raise HTTPException(404, "Treino não encontrado")
    if activity.stream is None:
        raise HTTPException(422, "Esse treino não tem série temporal guardada.")

    settings = get_settings()
    payload = activity.stream.payload
    result = analysis.analyze(payload, settings.ftp_watts)

    # A analise nao sabe o que e uma bike, e nao deve saber. Quem cruza as duas
    # coisas e o router: de um lado o que o pedal mediu, do outro o que a maquina
    # tem. Sem transmissao declarada a chave nem aparece, e a tela nao desenha a
    # secao - mesmo padrao do mapa quando o .fit nao tem GPS.
    bike = activity.bike
    if bike and bike.chainrings and bike.cassette and bike.wheel_circumference_mm:
        if result.get("gears", {}).get("available"):
            groups = drivetrain.collapse(
                drivetrain.gear_table(bike.chainrings, bike.cassette, bike.wheel_circumference_mm)
            )
            cobertura = drivetrain.coverage(
                payload.get("cadence"),
                payload.get("speed"),
                groups,
                analysis.sample_rate_of(payload),
            )
            if cobertura:
                result["gears"]["coverage"] = cobertura

    return result


@router.get("/{activity_id}/route")
def activity_route(activity_id: int, db: Session = Depends(get_db)):
    """Coordenadas do trajeto para o mapa, com as metricas ponto a ponto."""
    activity = db.get(Activity, activity_id)
    if activity is None:
        raise HTTPException(404, "Treino não encontrado")
    if activity.stream is None:
        raise HTTPException(422, "Sem série temporal.")

    payload = activity.stream.payload
    lat = payload.get("lat") or []
    lon = payload.get("lon") or []
    if not lat or not lon:
        return {
            "available": False,
            "reason": "Esse .fit não tem GPS. Treino de rolo ou ciclocomputador sem sinal costumam ficar assim.",
        }

    points = []
    for index, (la, lo) in enumerate(zip(lat, lon)):
        if la is None or lo is None or (la == 0 and lo == 0):
            continue
        points.append(
            {
                "i": index,
                "lat": round(la, 6),
                "lon": round(lo, 6),
                "speed": _at(payload.get("speed"), index),
                "hr": _at(payload.get("hr"), index),
                "power": _at(payload.get("power"), index),
                "cadence": _at(payload.get("cadence"), index),
                "altitude": _at(payload.get("altitude"), index),
                "km": _at(payload.get("distance"), index),
            }
        )

    if not points:
        return {"available": False, "reason": "As coordenadas vieram vazias neste arquivo."}

    lats = [p["lat"] for p in points]
    lons = [p["lon"] for p in points]
    return {
        "available": True,
        "points": points,
        "bounds": {"south": min(lats), "north": max(lats), "west": min(lons), "east": max(lons)},
    }


@router.get("/{activity_id}/similar-segments")
def similar_segments(activity_id: int, radius_m: int = 150, db: Session = Depends(get_db)):
    """Acha subidas parecidas em outros treinos e compara os tempos.

    O casamento e feito pelo ponto de partida no mapa: se voce comecou a subir
    a menos de 150 m do mesmo lugar e a subida tem comprimento parecido, e a mesma
    ladeira. Da para ver se voce esta subindo mais rapido do que mes passado.
    """
    activity = db.get(Activity, activity_id)
    if activity is None or activity.stream is None:
        raise HTTPException(404, "Treino não encontrado")

    settings = get_settings()
    current = analysis.analyze(activity.stream.payload, settings.ftp_watts)
    if not current.get("available"):
        return {"comparisons": []}

    climbs = [s for s in current["segments"] if s["terrain"] == "subida" and s["distance_m"] >= 400 and s["lat"]]
    if not climbs:
        return {"comparisons": []}

    others = db.scalars(select(Activity).where(Activity.id != activity_id).order_by(Activity.started_at.desc()).limit(30))
    history: list[tuple[Activity, list[dict]]] = []
    for other in others:
        if other.stream is None:
            continue
        result = analysis.analyze(other.stream.payload, settings.ftp_watts)
        if result.get("available"):
            history.append((other, [s for s in result["segments"] if s["terrain"] == "subida" and s["lat"]]))

    comparisons = []
    for climb in climbs:
        matches = []
        for other, other_climbs in history:
            for candidate in other_climbs:
                if _distance_m(climb["lat"], climb["lon"], candidate["lat"], candidate["lon"]) > radius_m:
                    continue
                if abs(candidate["distance_m"] - climb["distance_m"]) > climb["distance_m"] * 0.25:
                    continue
                matches.append(
                    {
                        "activity_id": other.id,
                        "date": other.started_at.date().isoformat(),
                        "duration_s": candidate["duration_s"],
                        "vam": candidate["vam"],
                        "avg_power": candidate["avg_power"],
                        "avg_hr": candidate["avg_hr"],
                    }
                )
        if matches:
            best = min(matches, key=lambda m: m["duration_s"])
            delta = climb["duration_s"] - best["duration_s"]
            comparisons.append(
                {
                    "segment": climb,
                    "attempts": sorted(matches, key=lambda m: m["duration_s"])[:5],
                    "personal_best_s": best["duration_s"],
                    "delta_s": round(delta),
                    "verdict": _climb_verdict(delta, best["date"]),
                }
            )

    return {"comparisons": comparisons}


def _climb_verdict(delta_s: float, best_date: str) -> str:
    if delta_s < -3:
        return f"Recorde novo: {abs(delta_s):.0f}s mais rápido do que seu melhor tempo aqui."
    if delta_s > 3:
        return f"{delta_s:.0f}s mais lento que seu melhor tempo nesta subida, feito em {best_date}."
    return "Praticamente empatado com seu melhor tempo nesta subida."


def _at(stream: list | None, index: int):
    if not stream or index >= len(stream):
        return None
    return stream[index]


# Trechos escolhidos nao podem se sobrepor: 15% do pedal entre um e outro.
_ADVICE_SPREAD = 0.15


@router.get("/{activity_id}/route-advice")
def route_advice(activity_id: int, refresh: bool = False, db: Session = Depends(get_db)):
    """Tela Tecnica, mapa do treino: os 3 trechos mais melhoraveis do percurso,
    cada um ancorado a um ponto do mapa (lat/lon) com o problema (factual) e a
    dica de como melhorar ali (IA local)."""
    activity = db.get(Activity, activity_id)
    if activity is None:
        raise HTTPException(404, "Treino não encontrado")
    if activity.stream is None:
        raise HTTPException(422, "Esse treino não tem série temporal guardada.")

    settings = get_settings()
    payload = activity.stream.payload
    if not (payload.get("lat") and payload.get("lon")):
        return {"available": False, "reason": "Esse .fit não tem GPS — sem mapa, sem dicas no percurso."}

    result = analysis.analyze(payload, settings.ftp_watts)
    if not result.get("available"):
        return {"available": False, "reason": result.get("reason", "Treino curto demais para analisar.")}

    ranking = result["highlights"].get("ranking") or []
    baseline = result["baseline"]
    n = len(payload.get("t") or []) or 1

    # Os 3 piores por rendimento (score baixo), com GPS e sem se sobrepor.
    gap = max(1, int(n * _ADVICE_SPREAD))
    escolhidos: list[dict] = []
    for seg in sorted(ranking, key=lambda c: c.get("score", 100)):
        if seg.get("lat") is None or seg.get("lon") is None:
            continue
        if any(abs(seg["start_index"] - c["start_index"]) < gap for c in escolhidos):
            continue
        escolhidos.append(seg)
        if len(escolhidos) == 3:
            break

    if not escolhidos:
        return {"available": False, "reason": "Não há trechos pedalados longos o bastante para apontar no mapa."}

    pontos = []
    for ordem, seg in enumerate(escolhidos, 1):
        motivos = analysis.explain(seg, baseline, seg["end_index"] / n, False)
        problema = motivos[0]["text"] if motivos else (
            f"{seg['terrain'].capitalize()} de {seg['gradient']}%, cadência {seg.get('avg_cadence')} rpm."
        )
        pontos.append(
            {
                "order": ordem,
                "label": f"{seg['terrain'].capitalize()} · km {seg['start_km']}–{seg['end_km']}",
                "terrain": seg["terrain"],
                "gradient": seg["gradient"],
                "start_km": seg["start_km"],
                "end_km": seg["end_km"],
                "start_index": seg["start_index"],
                "end_index": seg["end_index"],
                "lat": seg["lat"],
                "lon": seg["lon"],
                "avg_cadence": seg.get("avg_cadence"),
                "avg_power": seg.get("avg_power"),
                "torque_nm": seg.get("torque_nm"),
                "problema": problema,
            }
        )

    key = (settings.ollama_model, activity_id, settings.ftp_watts)
    cached = None if refresh else _route_advice_cache.get(key)
    if cached is None and settings.ollama_enabled:
        dicas = insight_service.route_dicas(pontos, settings.ollama_host, settings.ollama_model)
        if dicas:
            cached = {"dicas": dicas, "generated_at": _now_iso()}
            _route_advice_cache[key] = cached

    dicas = cached["dicas"] if cached else []
    for i, p in enumerate(pontos):
        p["dica"] = dicas[i] if i < len(dicas) else None

    return {
        "available": True,
        "points": pontos,
        "dicas_available": cached is not None,
        "model": settings.ollama_model,
        "generated_at": cached["generated_at"] if cached else None,
    }


def _now_iso() -> str:
    from datetime import datetime

    return datetime.utcnow().isoformat()


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine simplificado - preciso o bastante para distancias curtas."""
    from math import asin, cos, radians, sin, sqrt

    r = 6371000
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    return 2 * r * asin(sqrt(a))
