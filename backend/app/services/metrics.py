"""Metricas de treino calculadas a partir das series do .fit.

Referencias usuais do ciclismo:
  NP  = media movel de 30s da potencia, elevada a 4, media, raiz quarta
  IF  = NP / FTP
  TSS = (tempo_s * NP * IF) / (FTP * 3600) * 100
  CTL = media exponencial de 42 dias do TSS  (condicionamento)
  ATL = media exponencial de 7 dias do TSS   (fadiga)
  TSB = CTL - ATL                            (forma)
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np

# Duracoes (em segundos) da curva de potencia / melhores esforcos
POWER_CURVE_WINDOWS = [1, 5, 15, 30, 60, 120, 300, 600, 1200, 1800, 3600]

# Zonas de potencia por % do FTP (modelo Coggan)
POWER_ZONES = [
    ("Z1 Recuperacao", 0.00, 0.55),
    ("Z2 Endurance", 0.55, 0.75),
    ("Z3 Tempo", 0.75, 0.90),
    ("Z4 Limiar", 0.90, 1.05),
    ("Z5 VO2max", 1.05, 1.20),
    ("Z6 Anaerobico", 1.20, 1.50),
    ("Z7 Neuromuscular", 1.50, 99.0),
]

# Zonas de FC por % da FC maxima
HR_ZONES = [
    ("Z1", 0.00, 0.60),
    ("Z2", 0.60, 0.70),
    ("Z3", 0.70, 0.80),
    ("Z4", 0.80, 0.90),
    ("Z5", 0.90, 2.00),
]


def _clean(values: list | None) -> np.ndarray:
    if not values:
        return np.array([], dtype=float)
    arr = np.array([v if v is not None else np.nan for v in values], dtype=float)
    return arr


def normalized_power(power: list | None, sample_rate_s: float = 1.0) -> float | None:
    arr = _clean(power)
    if arr.size == 0 or np.all(np.isnan(arr)):
        return None
    arr = np.nan_to_num(arr, nan=0.0)
    window = max(1, int(round(30 / sample_rate_s)))
    if arr.size < window:
        return float(round(arr.mean(), 1))
    kernel = np.ones(window) / window
    rolling = np.convolve(arr, kernel, mode="valid")
    np_value = float(np.mean(rolling**4) ** 0.25)
    return round(np_value, 1)


def training_stress(np_value: float | None, duration_s: float, ftp: int) -> tuple[float | None, float | None]:
    if not np_value or not duration_s or not ftp:
        return None, None
    intensity = np_value / ftp
    tss = (duration_s * np_value * intensity) / (ftp * 3600) * 100
    return round(intensity, 3), round(tss, 1)


def trimp(hr: list | None, duration_s: float, hr_rest: int, hr_max: int) -> float | None:
    """TRIMP de Banister - carga baseada em FC, util quando nao ha potenciometro."""
    arr = _clean(hr)
    if arr.size == 0 or np.all(np.isnan(arr)) or hr_max <= hr_rest:
        return None
    avg_hr = float(np.nanmean(arr))
    reserve = (avg_hr - hr_rest) / (hr_max - hr_rest)
    reserve = min(max(reserve, 0.0), 1.0)
    minutes = duration_s / 60
    return round(minutes * reserve * 0.64 * float(np.exp(1.92 * reserve)), 1)


def power_curve(power: list | None, sample_rate_s: float = 1.0) -> dict[str, float]:
    """Melhor potencia media para cada janela de tempo (mean maximal power)."""
    arr = _clean(power)
    if arr.size == 0 or np.all(np.isnan(arr)):
        return {}
    arr = np.nan_to_num(arr, nan=0.0)
    cumulative = np.concatenate([[0.0], np.cumsum(arr)])
    out: dict[str, float] = {}
    for seconds in POWER_CURVE_WINDOWS:
        n = max(1, int(round(seconds / sample_rate_s)))
        if arr.size < n:
            continue
        window_sums = cumulative[n:] - cumulative[:-n]
        out[str(seconds)] = round(float(window_sums.max() / n), 1)
    return out


def time_in_zones(values: list | None, bands: list, reference: float, sample_rate_s: float = 1.0) -> dict[str, float]:
    arr = _clean(values)
    if arr.size == 0 or np.all(np.isnan(arr)) or not reference:
        return {}
    arr = arr[~np.isnan(arr)]
    ratios = arr / reference
    out: dict[str, float] = {}
    for name, low, high in bands:
        count = int(np.sum((ratios >= low) & (ratios < high)))
        out[name] = round(count * sample_rate_s, 1)
    return out


def variability_index(np_value: float | None, avg_power: float | None) -> float | None:
    if not np_value or not avg_power:
        return None
    return round(np_value / avg_power, 3)


def performance_management(
    daily_load: dict[date, float], start: date, end: date, ctl_days: int = 42, atl_days: int = 7
) -> list[dict]:
    """Serie diaria de CTL / ATL / TSB entre duas datas."""
    ctl_k = 1 - np.exp(-1 / ctl_days)
    atl_k = 1 - np.exp(-1 / atl_days)
    ctl = atl = 0.0
    series = []
    day = start
    while day <= end:
        load = daily_load.get(day, 0.0)
        ctl = ctl + (load - ctl) * ctl_k
        atl = atl + (load - atl) * atl_k
        series.append(
            {
                "date": day.isoformat(),
                "load": round(load, 1),
                "ctl": round(ctl, 1),
                "atl": round(atl, 1),
                "tsb": round(ctl - atl, 1),
            }
        )
        day += timedelta(days=1)
    return series


# --------------------------------------------------------------------------
# Resumo de relevo, no mesmo vocabulario que o app do iGPSPORT usa
# --------------------------------------------------------------------------


def _smooth_edges(values: np.ndarray, window: int) -> np.ndarray:
    """Media movel com bordas replicadas.

    Usar mode="same" do numpy aqui seria um desastre silencioso: ele preenche as
    pontas com ZERO, entao os primeiros e ultimos segundos de todo treino cairiam
    de 21 m de altitude para perto de 0. Isso inventa uma rampa que nunca existiu,
    e ela contamina inclinacao, VAM e potencia estimada do inicio e do fim de todo
    pedal. Replicar a borda mantem o comeco e o fim honestos.
    """
    if values.size < 2 or window < 2:
        return values
    window = min(window, values.size)
    pad = window // 2
    padded = np.pad(values, (pad, pad), mode="edge")
    kernel = np.ones(window) / window
    smoothed = np.convolve(padded, kernel, mode="valid")
    return smoothed[: values.size]


def terrain_summary(altitude: list | None, distance_km: list | None, duration_s: float) -> dict:
    """Grau+/Grau-, VAM+ e faixa de altitude - os campos da tela de resumo do app."""
    if not altitude or not distance_km:
        return {}

    alt = np.array([v if v is not None else np.nan for v in altitude], dtype=float)
    dist = np.array([v if v is not None else np.nan for v in distance_km], dtype=float) * 1000
    if np.all(np.isnan(alt)) or np.all(np.isnan(dist)):
        return {}

    alt = np.nan_to_num(alt, nan=float(np.nanmean(alt)))
    dist = np.nan_to_num(dist, nan=0.0)

    n = alt.size

    # Janelas em SEGUNDOS de pedal, nao em amostras. Com "smart recording" (um
    # ponto a cada 1 a 8 s) 15 amostras viravam 100+ s de estrada e a inclinacao
    # era alisada ate quase sumir: num pedal real o Grau+ maximo saia 2,1% quando
    # o proprio aparelho gravou 7,65%, e o VAM+ saia pela metade. A 1 Hz o
    # resultado e identico ao de antes.
    seconds_per_sample = duration_s / n if duration_s > 0 and n else 1.0
    smooth_window = max(2, int(round(15 / max(seconds_per_sample, 0.01))))
    smooth_alt = _smooth_edges(alt, smooth_window) if n > smooth_window else alt

    # Inclinacao em janela larga - ponto a ponto o barometro inventa rampas.
    gradient = np.zeros(n)
    window = max(1, int(round(10 / max(seconds_per_sample, 0.01))))
    for i in range(n):
        lo, hi = max(0, i - window), min(n - 1, i + window)
        run = dist[hi] - dist[lo]
        if run > 5:
            gradient[i] = (smooth_alt[hi] - smooth_alt[lo]) / run * 100
    gradient = np.clip(gradient, -25, 25)

    up = gradient[gradient > 0.5]
    down = gradient[gradient < -0.5]

    deltas = np.diff(smooth_alt)
    ascent = float(deltas[deltas > 0].sum())
    descent = float(deltas[deltas < 0].sum())

    # VAM: metros verticais por hora. So faz sentido enquanto voce esta subindo.
    vam_up_avg = vam_up_max = None
    if duration_s > 0 and n > 1:
        climbing = gradient[1:] > 0.5
        rises = deltas[climbing]
        climbing_ascent = float(rises[rises > 0].sum())
        climbing_time = float(np.sum(climbing)) * seconds_per_sample
        if climbing_time > 60 and climbing_ascent > 0:
            vam_up_avg = round(climbing_ascent / climbing_time * 3600, 0)
        # VAM+ Max: pico de subida numa janela curta. Janela de 1 minuto diluiria
        # o kicker de 20 segundos, que e justamente o que o numero deveria mostrar.
        vam_window = max(2, int(round(20 / max(seconds_per_sample, 0.01))))
        if n > vam_window:
            step = max(1, n // 300)
            rates = []
            for i in range(0, n - vam_window, step):
                # So janelas que sao subida de verdade. Sem esse filtro, um trecho
                # plano no meio da janela derruba a taxa e o "maximo" acaba ficando
                # menor que a media - que so conta tempo subindo.
                if np.mean(gradient[i : i + vam_window] > 0.5) < 0.8:
                    continue
                rise = smooth_alt[i + vam_window] - smooth_alt[i]
                if rise > 0:
                    rates.append(rise / (vam_window * seconds_per_sample) * 3600)
            if rates:
                vam_up_max = round(float(np.percentile(rates, 98)), 0)

    return {
        "descent_m": round(abs(descent), 0),
        "grade_up_avg": round(float(up.mean()), 1) if up.size else None,
        "grade_up_max": round(float(np.percentile(up, 98)), 1) if up.size else None,
        "grade_down_avg": round(float(down.mean()), 1) if down.size else None,
        "grade_down_max": round(float(np.percentile(down, 2)), 1) if down.size else None,
        "vam_up_avg": vam_up_avg,
        "vam_up_max": vam_up_max,
        "altitude_min": round(float(alt.min()), 0),
        "altitude_avg": round(float(alt.mean()), 0),
        "altitude_max": round(float(alt.max()), 0),
    }
