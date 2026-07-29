"""Leitura de arquivos .fit exportados do iGPSPORT.

O .fit e um padrao da Garmin/ANT+, entao o mesmo parser serve para arquivos
do iGPSPORT, Garmin, Wahoo, Bryton etc.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fitdecode

SEMICIRCLE_TO_DEG = 180 / 2**31

# Campos de record que interessam para o grafico
RECORD_FIELDS = {
    "timestamp": "t",
    "distance": "distance",
    "speed": "speed",
    "enhanced_speed": "speed",
    "altitude": "altitude",
    "enhanced_altitude": "altitude",
    "heart_rate": "hr",
    "cadence": "cadence",
    "power": "power",
    "temperature": "temperature",
    "position_lat": "lat",
    "position_long": "lon",
    "grade": "grade",
}


@dataclass
class ParsedActivity:
    file_name: str
    file_hash: str
    started_at: datetime
    sport: str = "cycling"
    device: str | None = None
    duration_s: float = 0.0
    moving_time_s: float = 0.0
    distance_km: float = 0.0
    elevation_gain_m: float = 0.0
    descent_m: float | None = None
    calories: int | None = None
    avg_speed_kmh: float | None = None
    max_speed_kmh: float | None = None
    avg_hr: float | None = None
    max_hr: float | None = None
    avg_cadence: float | None = None
    avg_power: float | None = None
    max_power: float | None = None
    avg_temperature: float | None = None
    max_temperature: float | None = None
    max_cadence: float | None = None
    streams: dict[str, list] = field(default_factory=dict)
    sample_rate_s: float = 1.0
    sensors: list[dict] = field(default_factory=list)
    sensor_signature: str | None = None


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get(frame, name):
    try:
        if frame.has_field(name):
            return frame.get_value(name)
    except KeyError:
        return None
    return None


def utc_offset(activity_utc, activity_local) -> timedelta | None:
    """Descobre o fuso onde o pedal aconteceu, a partir do proprio arquivo.

    A mensagem `activity` do .fit grava a mesma hora duas vezes: `timestamp` em
    UTC e `local_timestamp` no relogio de parede do aparelho. A diferenca entre
    as duas e o fuso do ciclista no dia do treino - melhor do que o fuso do
    servidor, que pode nem ser o mesmo.

    Sem isso, um pedal das 18:22 e gravado como 21:22, e um pedal que comeca
    depois das 21h aparece com a data do dia seguinte.
    """
    if not isinstance(activity_utc, datetime) or not isinstance(activity_local, datetime):
        return None
    utc = activity_utc.astimezone(timezone.utc).replace(tzinfo=None) if activity_utc.tzinfo else activity_utc
    local = activity_local.replace(tzinfo=None) if activity_local.tzinfo else activity_local

    # Todo fuso real e multiplo de 15 min; arredondar absorve o segundo de
    # diferenca entre a gravacao de um campo e a do outro.
    offset = timedelta(seconds=round((local - utc).total_seconds() / 900) * 900)
    if -timedelta(hours=12) <= offset <= timedelta(hours=14):
        return offset
    return None  # fora da faixa de fusos que existem: campo corrompido


def parse_fit(path: Path) -> ParsedActivity:
    records: list[dict] = []
    session: dict = {}
    devices: list[dict] = []
    device_name: str | None = None
    activity_utc = activity_local = None

    with fitdecode.FitReader(str(path)) as fit:
        for frame in fit:
            if frame.frame_type != fitdecode.FIT_FRAME_DATA:
                continue

            if frame.name == "record":
                row: dict = {}
                for fit_field, key in RECORD_FIELDS.items():
                    value = _get(frame, fit_field)
                    if value is None:
                        continue
                    if key in ("lat", "lon") and isinstance(value, (int, float)):
                        value = value * SEMICIRCLE_TO_DEG
                    row.setdefault(key, value)
                if row:
                    records.append(row)

            elif frame.name == "session":
                for fit_field in (
                    "start_time",
                    "sport",
                    "total_elapsed_time",
                    "total_timer_time",
                    "total_distance",
                    "total_ascent",
                    "total_descent",
                    "total_calories",
                    "avg_speed",
                    "enhanced_avg_speed",
                    "max_speed",
                    "enhanced_max_speed",
                    "avg_heart_rate",
                    "max_heart_rate",
                    "avg_cadence",
                    "max_cadence",
                    "max_temperature",
                    "avg_power",
                    "max_power",
                    "avg_temperature",
                ):
                    value = _get(frame, fit_field)
                    if value is not None:
                        session.setdefault(fit_field, value)

            elif frame.name == "device_info":
                entry = {
                    "device_index": _get(frame, "device_index"),
                    "device_type": _get(frame, "antplus_device_type") or _get(frame, "device_type"),
                    "manufacturer": _get(frame, "manufacturer"),
                    "product": _get(frame, "product_name") or _get(frame, "garmin_product") or _get(frame, "product"),
                    "serial_number": _get(frame, "serial_number"),
                    "ant_device_number": _get(frame, "ant_device_number"),
                    "battery_status": _get(frame, "battery_status"),
                }
                if any(v is not None for v in entry.values()):
                    devices.append({k: (str(v) if v is not None else None) for k, v in entry.items()})

            elif frame.name == "activity":
                activity_utc = _get(frame, "timestamp")
                activity_local = _get(frame, "local_timestamp")

            elif frame.name == "file_id" and device_name is None:
                for fit_field in ("product_name", "garmin_product", "product", "manufacturer"):
                    value = _get(frame, fit_field)
                    if value:
                        device_name = str(value)
                        break

    if not records and not session:
        raise ValueError("Arquivo .fit sem registros de treino")

    timestamps = [r["t"] for r in records if isinstance(r.get("t"), datetime)]
    started_at = session.get("start_time") or (timestamps[0] if timestamps else None)
    if started_at is None:
        raise ValueError("Não foi possível determinar a data do treino")
    if isinstance(started_at, datetime) and started_at.tzinfo is not None:
        started_at = started_at.astimezone(timezone.utc).replace(tzinfo=None)

    # started_at passa a guardar a HORA LOCAL DO PEDAL, nao UTC: e ela que voce
    # reconhece na lista de treinos. Quando o arquivo nao traz local_timestamp,
    # sobra o UTC mesmo - melhor um horario deslocado do que um chute de fuso.
    offset = utc_offset(activity_utc, activity_local)
    if offset is not None:
        started_at = started_at + offset

    # Amostragem: alguns aparelhos gravam "smart recording" e nao 1Hz
    sample_rate = 1.0
    if len(timestamps) > 2:
        span = (timestamps[-1] - timestamps[0]).total_seconds()
        if span > 0:
            sample_rate = max(0.5, round(span / (len(timestamps) - 1), 2))

    streams: dict[str, list] = {}
    keys = ["t", "distance", "speed", "altitude", "hr", "cadence", "power", "temperature", "lat", "lon"]
    base_t = timestamps[0] if timestamps else None
    for key in keys:
        column = []
        for r in records:
            value = r.get(key)
            if key == "t":
                value = round((value - base_t).total_seconds(), 1) if isinstance(value, datetime) and base_t else None
            elif key == "speed" and value is not None:
                value = round(float(value) * 3.6, 2)  # m/s -> km/h
            elif key == "distance" and value is not None:
                value = round(float(value) / 1000, 4)  # m -> km
            elif value is not None:
                value = _as_float(value)
            column.append(value)
        if any(v is not None for v in column):
            streams[key] = column

    duration = _as_float(session.get("total_elapsed_time")) or (
        (timestamps[-1] - timestamps[0]).total_seconds() if len(timestamps) > 1 else 0.0
    )
    moving = _as_float(session.get("total_timer_time")) or duration

    distance_km = _as_float(session.get("total_distance"))
    distance_km = distance_km / 1000 if distance_km else (streams.get("distance") or [0])[-1] or 0.0

    ascent = _as_float(session.get("total_ascent"))
    if ascent is None:
        ascent = _elevation_gain(streams.get("altitude", []))
    descent = _as_float(session.get("total_descent"))

    def avg(key, skip_zeros=False):
        column = [v for v in streams.get(key, []) if v is not None]
        if skip_zeros:
            # O app do iGPSPORT mostra "Cadencia Media" contando so o tempo pedalando.
            # Incluir os zeros de semaforo derruba o numero e nao descreve seu giro.
            column = [v for v in column if v > 0]
        return round(sum(column) / len(column), 1) if column else None

    def peak(key):
        column = [v for v in streams.get(key, []) if v is not None]
        return round(max(column), 1) if column else None

    avg_speed = _as_float(session.get("enhanced_avg_speed") or session.get("avg_speed"))
    max_speed = _as_float(session.get("enhanced_max_speed") or session.get("max_speed"))

    sensors = dedupe_sensors(devices)
    signature = sensor_signature(sensors)
    if device_name is None:
        head = next((s for s in sensors if s.get("device_index") in ("0", "creator")), None)
        if head:
            device_name = head.get("product") or head.get("manufacturer")

    return ParsedActivity(
        file_name=path.name,
        file_hash=file_hash(path),
        started_at=started_at,
        sport=str(session.get("sport") or "cycling"),
        device=device_name,
        duration_s=round(duration or 0, 1),
        moving_time_s=round(moving or 0, 1),
        distance_km=round(distance_km or 0, 3),
        elevation_gain_m=round(ascent or 0, 1),
        descent_m=round(descent, 1) if descent else None,
        calories=int(session["total_calories"]) if session.get("total_calories") else None,
        avg_speed_kmh=round(avg_speed * 3.6, 2) if avg_speed else avg("speed"),
        max_speed_kmh=round(max_speed * 3.6, 2) if max_speed else peak("speed"),
        avg_hr=_as_float(session.get("avg_heart_rate")) or avg("hr"),
        max_hr=_as_float(session.get("max_heart_rate")) or peak("hr"),
        avg_cadence=_as_float(session.get("avg_cadence")) or avg("cadence", skip_zeros=True),
        avg_power=_as_float(session.get("avg_power")) or avg("power"),
        max_power=_as_float(session.get("max_power")) or peak("power"),
        avg_temperature=_as_float(session.get("avg_temperature")) or avg("temperature"),
        max_temperature=_as_float(session.get("max_temperature")) or peak("temperature"),
        max_cadence=_as_float(session.get("max_cadence")) or peak("cadence"),
        streams=streams,
        sample_rate_s=sample_rate,
        sensors=sensors,
        sensor_signature=signature,
    )


def _elevation_gain(altitude: list, threshold: float = 1.0) -> float:
    """Soma so as subidas, ignorando ruido do barometro abaixo do threshold."""
    clean = [v for v in altitude if v is not None]
    if len(clean) < 2:
        return 0.0
    gain = 0.0
    reference = clean[0]
    for value in clean[1:]:
        delta = value - reference
        if delta >= threshold:
            gain += delta
            reference = value
        elif delta < 0:
            reference = value
    return round(gain, 1)


def downsample(streams: dict[str, list], max_points: int = 1200) -> dict[str, list]:
    """Reduz a serie para o grafico do frontend nao engasgar."""
    length = max((len(v) for v in streams.values()), default=0)
    if length <= max_points:
        return streams
    step = length // max_points + 1
    return {key: values[::step] for key, values in streams.items()}


# --------------------------------------------------------------------------
# Sensores: a "impressao digital" de cada bike
# --------------------------------------------------------------------------
# Todo sensor ANT+/BLE emparelhado (cadencia, velocidade, potenciometro) grava
# um device_info no .fit com um numero de serie unico. Como esses sensores ficam
# parafusados numa bike so, o conjunto deles identifica a bike melhor do que o
# modelo declarado: e ela quem se apresenta, nao voce que precisa lembrar.

# Sensores que ficam presos a bike (identificam a maquina).
BIKE_BOUND_TYPES = {
    "bike_speed",
    "bike_cadence",
    "bike_speed_cadence",
    "bike_power",
    "11",  # bike_power
    "120",  # heart_rate (ignorado abaixo)
    "121",  # bike_speed_cadence
    "122",  # bike_cadence
    "123",  # bike_speed
}

# Sensores que ficam no corpo do ciclista - nao dizem nada sobre a bike.
BODY_BOUND_TYPES = {"heart_rate", "120", "stride_speed_distance", "running_dynamics"}


def dedupe_sensors(devices: list[dict]) -> list[dict]:
    """O .fit repete device_info a cada poucos minutos. Guarda so um de cada."""
    seen: dict[str, dict] = {}
    for entry in devices:
        key = "|".join(
            str(entry.get(field) or "")
            for field in ("manufacturer", "product", "serial_number", "ant_device_number", "device_type")
        )
        if key.strip("|") and key not in seen:
            seen[key] = entry
    return list(seen.values())


def sensor_signature(sensors: list[dict]) -> str | None:
    """Assinatura estavel dos sensores presos a bike.

    Usa so o identificador de radio (serial/ANT id) dos sensores de bike. O
    monitor cardiaco fica de fora de proposito: ele vai com voce, nao com a bike,
    entao incluir ele faria a mesma bike parecer duas quando a cinta descarrega.
    """
    ids = []
    for sensor in sensors:
        device_type = str(sensor.get("device_type") or "").lower()
        if device_type in BODY_BOUND_TYPES:
            continue
        if str(sensor.get("device_index") or "") in ("0", "creator"):
            continue  # o proprio ciclocomputador troca de bike com voce
        radio_id = sensor.get("ant_device_number") or sensor.get("serial_number")
        if radio_id:
            ids.append(str(radio_id))
    if not ids:
        return None
    return "|".join(sorted(set(ids)))
