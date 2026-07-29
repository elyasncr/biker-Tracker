"""Estima potencia a partir de velocidade, inclinacao e peso.

Por que isso existe: sem potenciometro e sem cinta cardiaca, nao ha como medir
carga de treino - TSS precisa de watt, TRIMP precisa de batimento. Sem nenhum dos
dois, o grafico de condicionamento fica vazio para sempre.

A saida: calcular a potencia pela fisica. Para manter a bike andando voce vence
tres forcas - o atrito do pneu, a gravidade na subida e o arrasto do ar - mais a
inercia quando acelera. Todas sao calculaveis com velocidade, inclinacao e massa,
que e exatamente o que o BSC100S grava.

Precisao: a estimativa erra tipicamente de 10 a 15% contra um potenciometro real,
e erra mais com vento forte (o modelo assume ar parado) e em descida tecnica. Mas
ela erra de forma *consistente*, e consistencia e o que importa para acompanhar
evolucao. Se todo mes o numero e calculado do mesmo jeito, a comparacao entre os
meses continua valendo. O que voce nao pode fazer e comparar esse numero com o
potenciometro de um amigo.
"""

from __future__ import annotations

import numpy as np

GRAVITY = 9.8067
DRIVETRAIN_EFFICIENCY = 0.97

# Coeficientes por tipo de bike.
#   crr = resistencia de rolamento (pneu fino e liso rola mais facil)
#   cda = area frontal x arrasto (quanto mais ereto voce anda, mais vento pega)
BIKE_COEFFICIENTS = {
    "speed": {"crr": 0.005, "cda": 0.36},
    "gravel": {"crr": 0.007, "cda": 0.42},
    "mtb": {"crr": 0.012, "cda": 0.50},
    "urbana": {"crr": 0.008, "cda": 0.55},
}
DEFAULT_COEFFICIENTS = {"crr": 0.007, "cda": 0.45}


def air_density(altitude_m: float, temperature_c: float = 20.0) -> float:
    """Ar mais quente e mais alto e menos denso, entao empurra menos."""
    pressure = 101325 * (1 - 2.25577e-5 * max(altitude_m, 0)) ** 5.25588
    return pressure / (287.05 * (temperature_c + 273.15))


def estimate_power_stream(
    speed_kmh: list | None,
    altitude_m: list | None,
    distance_km: list | None,
    total_mass_kg: float,
    crr: float,
    cda: float,
    temperature_c: float = 20.0,
    sample_rate_s: float = 1.0,
) -> list[float | None] | None:
    """Devolve uma serie de potencia estimada, watt a watt."""
    if not speed_kmh:
        return None

    n = len(speed_kmh)
    speed = np.array([v if v is not None else np.nan for v in speed_kmh], dtype=float) / 3.6  # m/s
    if np.all(np.isnan(speed)):
        return None
    speed = np.nan_to_num(speed, nan=0.0)

    alt = np.zeros(n)
    if altitude_m:
        alt = np.array([v if v is not None else np.nan for v in altitude_m][:n], dtype=float)
        alt = np.nan_to_num(alt, nan=float(np.nanmean(alt)) if not np.all(np.isnan(alt)) else 0.0)
        alt = _smooth(alt, 15)  # barometro treme; sem alisar, a gravidade vira ruido

    dist_m = np.zeros(n)
    if distance_km:
        dist_m = np.nan_to_num(
            np.array([v if v is not None else np.nan for v in distance_km][:n], dtype=float), nan=0.0
        ) * 1000
    else:
        dist_m = np.cumsum(speed * sample_rate_s)

    # Inclinacao numa janela larga: 1 m de erro do barometro em 5 m de estrada
    # viraria 20% de rampa se calculado ponto a ponto.
    gradient = np.zeros(n)
    window = max(3, int(round(10 / sample_rate_s)))
    for i in range(n):
        lo = max(0, i - window)
        hi = min(n - 1, i + window)
        run = dist_m[hi] - dist_m[lo]
        if run > 5:
            gradient[i] = (alt[hi] - alt[lo]) / run
    gradient = np.clip(_smooth(gradient, 15), -0.25, 0.25)

    rho = air_density(float(np.mean(alt)), temperature_c)

    # Aceleracao: arrancar de um semaforo custa watt de verdade.
    acceleration = np.gradient(speed, sample_rate_s) if n > 2 else np.zeros(n)
    # Limite conservador: arrancada de semaforo faz a derivada explodir e o termo
    # inercial viraria picos de 1500 W que nunca existiram.
    acceleration = np.clip(_smooth(acceleration, 9), -0.8, 0.8)

    f_rolling = crr * total_mass_kg * GRAVITY * np.cos(np.arctan(gradient))
    f_gravity = total_mass_kg * GRAVITY * np.sin(np.arctan(gradient))
    f_drag = 0.5 * rho * cda * speed**2
    f_accel = total_mass_kg * acceleration

    power = (f_rolling + f_gravity + f_drag + f_accel) * speed / DRIVETRAIN_EFFICIENCY

    # Potencia negativa nao existe: descendo voce nao devolve energia ao pedal.
    power = np.clip(power, 0, 1200)
    power[speed < 0.5] = 0.0

    # Uma ultima alisada: o modelo responde rapido demais a ruido de GPS e
    # barometro, e picos de um segundo nao correspondem a nada real.
    power = _smooth(power, max(3, int(round(3 / sample_rate_s))))

    return [round(float(p), 1) for p in power]


def coefficients_for(kind: str | None, crr: float | None = None, cda: float | None = None) -> dict:
    base = BIKE_COEFFICIENTS.get(kind or "", DEFAULT_COEFFICIENTS)
    return {"crr": crr or base["crr"], "cda": cda or base["cda"]}


def estimate_ftp(best_20min_power: float | None) -> int | None:
    """FTP aproximado pelo melhor esforco de 20 minutos.

    A regra dos 95% e a convencao do teste de 20 min. Com potencia estimada ela
    herda o erro do modelo, entao serve como ponto de partida - nao como veredito.
    """
    if not best_20min_power:
        return None
    return int(round(best_20min_power * 0.95))


def _smooth(values: np.ndarray, window: int) -> np.ndarray:
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
