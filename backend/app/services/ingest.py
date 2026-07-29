"""Varre a pasta data/, le os .fit novos e grava no banco."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Activity, ActivityStream, SyncLog, WeightEntry
from . import metrics, power_model
from .bikes import match_bike
from .fit_parser import downsample, file_hash, parse_fit

log = logging.getLogger(__name__)


def scan_files(data_dir: Path) -> list[Path]:
    return sorted(p for p in data_dir.rglob("*") if p.suffix.lower() == ".fit" and p.is_file())


def _rider_weight_on(db: Session, quando: datetime) -> float:
    """Peso do ciclista na data do treino, ou o do .env se nao houver registro.

    O modelo de potencia usa a massa total na conta da fisica. Com um valor fixo,
    quem emagrece 8 kg segue tendo a potencia calculada com o corpo antigo - e a
    comparacao entre meses, que e o proposito do app, fica contaminada.
    """
    settings = get_settings()
    entries = list(db.scalars(select(WeightEntry)))
    if not entries:
        return settings.rider_weight_kg
    alvo = quando.date()
    mais_perto = min(entries, key=lambda e: abs((e.measured_on - alvo).days))
    return mais_perto.weight_kg


def import_file(db: Session, path: Path, force: bool = False) -> Activity | None:
    settings = get_settings()
    digest = file_hash(path)

    existing = db.scalar(select(Activity).where(Activity.file_hash == digest))
    if existing and not force:
        return None
    if existing and force:
        db.delete(existing)
        db.flush()

    parsed = parse_fit(path)
    streams = parsed.streams
    rate = parsed.sample_rate_s

    # A bike precisa ser identificada antes da potencia: peso, pneu e posicao
    # mudam a fisica, entao mudam a estimativa.
    bike = match_bike(db, parsed.sensor_signature)

    # Sem potenciometro, a potencia e calculada. Sem isso nao existe TSS, nao
    # existe curva de potencia e o grafico de condicionamento nunca sai do zero.
    power_estimated = False
    if not streams.get("power"):
        coeffs = power_model.coefficients_for(
            bike.kind if bike else None,
            bike.crr if bike else None,
            bike.cda if bike else None,
        )
        bike_weight = (bike.weight_kg if bike and bike.weight_kg else settings.default_bike_weight_kg)
        estimated = power_model.estimate_power_stream(
            speed_kmh=streams.get("speed"),
            altitude_m=streams.get("altitude"),
            distance_km=streams.get("distance"),
            total_mass_kg=_rider_weight_on(db, parsed.started_at) + bike_weight,
            crr=coeffs["crr"],
            cda=coeffs["cda"],
            temperature_c=parsed.avg_temperature or 20.0,
            sample_rate_s=rate,
        )
        if estimated:
            streams["power"] = estimated
            power_estimated = True
            # Media e maximo passam a vir da estimativa, senao ficariam vazios
            # enquanto NP e TSS apareceriam - o que confundiria mais do que ajuda.
            pedalling = [p for p in estimated if p is not None and p > 0]
            if pedalling:
                parsed.avg_power = round(sum(pedalling) / len(pedalling), 1)
                parsed.max_power = round(max(pedalling), 1)

    # Duracao ELAPSED, nao a do cronometro: a serie de registros cobre o pedal
    # inteiro, incluindo os semaforos. Usar o tempo em movimento aqui faria cada
    # amostra "valer" menos de um segundo e inflaria VAM e inclinacao.
    terrain = metrics.terrain_summary(streams.get("altitude"), streams.get("distance"), parsed.duration_s)
    # O declinio precisa sair do dict SEMPRE, nao so quando o aparelho traz o dele:
    # descent_m tambem e passado explicitamente para Activity() la embaixo, e deixar
    # a mesma chave nos dois lugares estoura "got multiple values for keyword
    # argument" e derruba o import inteiro do arquivo.
    calculated_descent = terrain.pop("descent_m", None)
    descent_m = parsed.descent_m or calculated_descent  # o valor do proprio aparelho ganha

    np_value = metrics.normalized_power(streams.get("power"), rate)
    intensity, tss = metrics.training_stress(np_value, parsed.moving_time_s, settings.ftp_watts)
    load = tss
    trimp_value = metrics.trimp(streams.get("hr"), parsed.moving_time_s, settings.hr_rest, settings.hr_max)
    if load is None and trimp_value is not None:
        load = trimp_value  # sem potenciometro, usa TRIMP como carga

    activity = Activity(
        source="fit",
        file_name=parsed.file_name,
        file_hash=parsed.file_hash,
        started_at=parsed.started_at,
        sport=parsed.sport,
        device=parsed.device,
        title=parsed.started_at.strftime("Pedal de %d/%m/%Y %H:%M"),
        duration_s=parsed.duration_s,
        moving_time_s=parsed.moving_time_s,
        distance_km=parsed.distance_km,
        elevation_gain_m=parsed.elevation_gain_m,
        calories=parsed.calories,
        avg_speed_kmh=parsed.avg_speed_kmh,
        max_speed_kmh=parsed.max_speed_kmh,
        avg_hr=parsed.avg_hr,
        max_hr=parsed.max_hr,
        avg_cadence=parsed.avg_cadence,
        avg_power=parsed.avg_power,
        max_power=parsed.max_power,
        avg_temperature=parsed.avg_temperature,
        normalized_power=np_value,
        intensity_factor=intensity,
        tss=load,
        variability_index=metrics.variability_index(np_value, parsed.avg_power),
        trimp=trimp_value,
        power_curve=metrics.power_curve(streams.get("power"), rate) or None,
        hr_zones_s=metrics.time_in_zones(streams.get("hr"), metrics.HR_ZONES, settings.hr_max, rate) or None,
        power_zones_s=metrics.time_in_zones(
            streams.get("power"), metrics.POWER_ZONES, settings.ftp_watts, rate
        )
        or None,
        sensors=parsed.sensors or None,
        sensor_signature=parsed.sensor_signature,
        max_cadence=parsed.max_cadence,
        descent_m=descent_m,
        max_temperature=parsed.max_temperature,
        power_is_estimated=power_estimated,
        **terrain,
    )
    if bike:
        activity.bike_id = bike.id
    db.add(activity)
    db.flush()
    db.add(ActivityStream(activity_id=activity.id, payload=downsample(streams)))
    return activity


def sync_folder(db: Session, force: bool = False) -> dict:
    settings = get_settings()
    files = scan_files(settings.data_path)
    imported, skipped, failures = 0, 0, []

    for path in files:
        try:
            result = import_file(db, path, force=force)
            if result is None:
                skipped += 1
            else:
                imported += 1
        except Exception as exc:  # arquivo corrompido nao pode derrubar a carga inteira
            log.exception("Falha ao importar %s", path)
            failures.append(f"{path.name}: {exc}")

    detail = "; ".join(failures) if failures else None
    db.add(SyncLog(source="fit", imported=imported, skipped=skipped, failed=len(failures), detail=detail))
    db.commit()

    return {
        "scanned": len(files),
        "imported": imported,
        "skipped": skipped,
        "failed": len(failures),
        "errors": failures,
        "data_dir": str(settings.data_path),
    }
