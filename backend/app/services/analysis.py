"""Analise estilo telemetria de F1: onde o pedal foi bem, onde foi mal, e por que.

A ideia central e a mesma da F1: ninguem aprende nada com o tempo total da volta.
O que ensina e o setor - "voce perdeu 3 decimos na curva 7 porque entrou devagar".
Aqui os "setores" sao trechos do trajeto detectados pelo relevo, e o "tempo" e a
eficiencia: quanto de potencia (ou velocidade) voce entregou por batimento.

Por que eficiencia e nao velocidade pura: velocidade depende de vento, transito e
inclinacao - ela mede a estrada, nao voce. Watt por batimento mede o motor. E o
mais perto que da para chegar de comparar uma subida com um plano no mesmo treino.
"""

from __future__ import annotations

import numpy as np

from . import drivetrain

# Um trecho precisa disso tudo para virar candidato a melhor/pior momento.
MIN_SEGMENT_S = 120
MIN_SEGMENT_M = 400
MAX_COASTING_RATIO = 0.30

CLIMB_THRESHOLD = 3.0  # % de inclinacao
DESCENT_THRESHOLD = -3.0

# Janelas em SEGUNDOS DE PEDAL, nunca em numero de amostras.
#
# O barometro treme numa escala de tempo, nao de amostras: alisar 15 segundos de
# altitude e o que mata o ruido. Enquanto o aparelho grava a 1 Hz as duas contas
# dao no mesmo, e foi por isso que a versao em amostras passou despercebida - mas
# o BSC100S grava em "smart recording", um ponto a cada 1 a 8 segundos, e a serie
# ainda e reduzida a 1200 pontos antes de ir para o banco. Nos dois casos 15
# amostras viram 100+ segundos de estrada, a inclinacao e alisada ate sumir e o
# pedal inteiro vira um trecho plano so - sem subida nenhuma para comparar.
#
# Medido num pedal real gravado a 7 s por amostra: a versao em amostras dava
# inclinacao maxima de 1,98%, a versao em segundos da 8,52%, e o proprio aparelho
# gravou 7,65%. A 1 Hz as duas versoes sao identicas.
SMOOTH_WINDOW_S = 15
GRADIENT_WINDOW_S = 10


def _samples_for(seconds: float, sample_rate_s: float, minimum: int = 1) -> int:
    """Quantas amostras cobrem esse tanto de segundos de pedal."""
    return max(minimum, int(round(seconds / max(sample_rate_s, 0.01))))

CADENCE_BANDS = [
    ("Abaixo de 60", 0, 60),
    ("60 a 70", 60, 70),
    ("70 a 80", 70, 80),
    ("80 a 90", 80, 90),
    ("90 a 100", 90, 100),
    ("Acima de 100", 100, 400),
]


def _arr(stream: list | None, length: int) -> np.ndarray:
    if not stream:
        return np.full(length, np.nan)
    values = [v if v is not None else np.nan for v in stream]
    values = values[:length] + [np.nan] * max(0, length - len(values))
    return np.array(values, dtype=float)


def _mean(values: np.ndarray) -> float | None:
    clean = values[~np.isnan(values)]
    return float(clean.mean()) if clean.size else None


def effective_sample_rate(time_s: np.ndarray) -> float:
    """Quantos segundos de pedal cada amostra guardada representa.

    Nao da para assumir 1 Hz aqui, por dois motivos que se somam:

    1. O ciclocomputador pode gravar em "smart recording" - o BSC100S grava um
       ponto a cada 1 a 8 segundos conforme o terreno, nao um por segundo.
    2. A serie e reduzida a 1200 pontos antes de ir para o banco (`downsample`),
       entao um pedal de 2 h guarda um ponto a cada 7 segundos.

    Assumir 1 Hz fazia tempo de barriga, marcha pesada e o grafico de cadencia
    sairem divididos por esse fator - num pedal de 44 min gravado a cada 7 s, os
    numeros apareciam sete vezes menores do que a realidade.

    A propria serie `t` guarda o tempo real de cada amostra, entao a taxa sai da
    mediana dos intervalos. Mediana e nao media porque pausa de semaforo cria
    intervalos gigantes que puxariam a media para cima.
    """
    clean = time_s[~np.isnan(time_s)]
    if clean.size < 2:
        return 1.0
    deltas = np.diff(clean)
    deltas = deltas[deltas > 0]
    if not deltas.size:
        return 1.0
    return float(np.median(deltas))


def sample_rate_of(streams: dict) -> float:
    """Taxa efetiva de amostragem da serie guardada, a partir do dicionario cru."""
    return effective_sample_rate(_arr(streams.get("t"), len(streams.get("t") or [])))


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
    values = np.nan_to_num(values, nan=float(np.nanmean(values)) if not np.all(np.isnan(values)) else 0.0)
    window = min(window, values.size)
    pad = window // 2
    padded = np.pad(values, (pad, pad), mode="edge")
    kernel = np.ones(window) / window
    smoothed = np.convolve(padded, kernel, mode="valid")
    return smoothed[: values.size]


# --------------------------------------------------------------------------
# Deteccao de trechos
# --------------------------------------------------------------------------


def detect_segments(
    distance_km: np.ndarray, altitude: np.ndarray, time_s: np.ndarray, sample_rate_s: float = 1.0
) -> list[dict]:
    """Corta o pedal em trechos de subida, plano e descida.

    O barometro treme muito, entao a altitude e alisada antes de virar inclinacao -
    sem isso o trajeto vira centenas de micro-trechos sem significado nenhum. As
    janelas sao convertidas de segundos para amostras conforme a taxa real de
    gravacao; ver SMOOTH_WINDOW_S.
    """
    n = distance_km.size
    if n < 30 or np.all(np.isnan(altitude)):
        return []

    smooth_window = _samples_for(SMOOTH_WINDOW_S, sample_rate_s, minimum=2)
    alt = _smooth(altitude, smooth_window)
    dist_m = np.nan_to_num(distance_km, nan=0.0) * 1000

    gradient = np.zeros(n)
    window = _samples_for(GRADIENT_WINDOW_S, sample_rate_s)
    for i in range(n):
        lo = max(0, i - window)
        hi = min(n - 1, i + window)
        run = dist_m[hi] - dist_m[lo]
        if run > 5:
            gradient[i] = (alt[hi] - alt[lo]) / run * 100
    gradient = np.clip(_smooth(gradient, smooth_window), -25, 25)

    kind = np.where(gradient > CLIMB_THRESHOLD, 1, np.where(gradient < DESCENT_THRESHOLD, -1, 0))

    # Junta trechos curtos demais ao vizinho: um repique de 50 m nao e uma subida.
    segments: list[dict] = []
    start = 0
    for i in range(1, n + 1):
        if i == n or kind[i] != kind[start]:
            length_m = dist_m[min(i, n - 1)] - dist_m[start]
            segments.append({"start": start, "end": min(i, n - 1), "kind": int(kind[start]), "length_m": length_m})
            start = i

    merged: list[dict] = []
    for seg in segments:
        if merged and seg["length_m"] < 200:
            merged[-1]["end"] = seg["end"]
            merged[-1]["length_m"] += seg["length_m"]
        else:
            merged.append(seg)

    return [
        {
            **seg,
            "gradient": float(np.nanmean(gradient[seg["start"] : seg["end"] + 1]))
            if seg["end"] > seg["start"]
            else 0.0,
            "terrain": {1: "subida", -1: "descida", 0: "plano"}[seg["kind"]],
        }
        for seg in merged
        if seg["end"] > seg["start"]
    ]


# --------------------------------------------------------------------------
# Metricas por trecho
# --------------------------------------------------------------------------


def segment_metrics(
    seg: dict,
    time_s: np.ndarray,
    distance_km: np.ndarray,
    altitude: np.ndarray,
    speed: np.ndarray,
    hr: np.ndarray,
    power: np.ndarray,
    cadence: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
) -> dict:
    a, b = seg["start"], seg["end"]
    sl = slice(a, b + 1)

    duration = float(time_s[b] - time_s[a]) if not np.isnan(time_s[b]) else 0.0
    distance_m = float(seg["length_m"])

    seg_power = power[sl]
    seg_cadence = cadence[sl]
    seg_hr = hr[sl]

    # Tempo de barriga: cadencia zero ou ausente com a bike andando.
    pedalling = seg_cadence[~np.isnan(seg_cadence)]
    coasting_ratio = float(np.mean(pedalling < 5)) if pedalling.size else 0.0

    avg_power = _mean(seg_power)
    avg_hr = _mean(seg_hr)
    avg_cadence = float(np.mean(pedalling[pedalling >= 5])) if pedalling[pedalling >= 5].size else None
    avg_speed = _mean(speed[sl])

    elevation = 0.0
    seg_alt = altitude[sl]
    clean_alt = seg_alt[~np.isnan(seg_alt)]
    if clean_alt.size > 1:
        deltas = np.diff(clean_alt)
        elevation = float(deltas[deltas > 0].sum())

    # VAM: metros de subida por hora. A moeda de quem sobe.
    vam = round(elevation / duration * 3600, 0) if duration > 0 and seg["kind"] == 1 else None

    # Variabilidade dentro do trecho: 1.0 e ritmo liso, acima de 1.15 e soco.
    clean_power = seg_power[~np.isnan(seg_power)]
    seg_vi = None
    if clean_power.size > 30 and avg_power:
        rolling = np.convolve(clean_power, np.ones(30) / 30, mode="valid")
        seg_np = float(np.mean(rolling**4) ** 0.25)
        seg_vi = round(seg_np / avg_power, 3) if avg_power else None

    # Torque na pedivela: quanta forca por pedalada, em Nm.
    torque = None
    if avg_power and avg_cadence and avg_cadence > 5:
        torque = round(avg_power / (2 * np.pi * avg_cadence / 60), 1)

    return {
        "terrain": seg["terrain"],
        "gradient": round(seg["gradient"], 1),
        "start_index": a,
        "end_index": b,
        "start_km": round(float(np.nan_to_num(distance_km[a])), 2),
        "end_km": round(float(np.nan_to_num(distance_km[b])), 2),
        "distance_m": round(distance_m, 0),
        "duration_s": round(duration, 0),
        "elevation_m": round(elevation, 0),
        "vam": vam,
        "avg_speed_kmh": round(avg_speed, 1) if avg_speed else None,
        "avg_power": round(avg_power, 0) if avg_power else None,
        "avg_hr": round(avg_hr, 0) if avg_hr else None,
        "avg_cadence": round(avg_cadence, 0) if avg_cadence else None,
        "torque_nm": torque,
        "variability": seg_vi,
        "coasting_ratio": round(coasting_ratio, 3),
        "lat": float(lat[a]) if not np.isnan(lat[a]) else None,
        "lon": float(lon[a]) if not np.isnan(lon[a]) else None,
        "end_lat": float(lat[b]) if not np.isnan(lat[b]) else None,
        "end_lon": float(lon[b]) if not np.isnan(lon[b]) else None,
    }


def efficiency(metrics: dict) -> float | None:
    """A nota do trecho. Tres niveis, do melhor para o possivel.

    1. Com potencia e FC: watt por batimento - mede o motor, custo incluido.
    2. So com FC: velocidade corrigida pela inclinacao, por batimento.
    3. Sem nenhum dos dois: potencia (real ou estimada) sozinha. Aqui a medida vira
       resultado, nao eficiencia - vento e semaforo entram na conta e nao ha como
       separar. E menos preciso, mas ainda diz onde voce andou melhor.
    """
    output = metrics.get("avg_power")
    cost = metrics.get("avg_hr")

    if output and cost:
        return output / cost
    if cost:
        speed = metrics.get("avg_speed_kmh")
        if not speed:
            return None
        gradient = metrics.get("gradient") or 0.0
        return speed * (1 + max(gradient, 0) * 0.14) / cost
    if output:
        return float(output)
    return None


# --------------------------------------------------------------------------
# Explicacoes: o "por conta de a, b, c"
# --------------------------------------------------------------------------


def explain(segment: dict, baseline: dict, ride_position: float, is_best: bool) -> list[dict]:
    """Traduz os numeros do trecho em frases com causa.

    Cada regra so fala quando a diferenca e grande o bastante para significar
    alguma coisa. Ruido nao vira explicacao - senao o texto mente com confianca.
    """
    reasons: list[dict] = []

    cad = segment.get("avg_cadence")
    base_cad = baseline.get("cadence")
    if cad and base_cad:
        delta = cad - base_cad
        if delta <= -8:
            reasons.append(
                {
                    "kind": "cadência",
                    "positive": False,
                    "impact": abs(delta),
                    "text": f"Cadência caiu para {cad:.0f} rpm, {abs(delta):.0f} abaixo do seu padrão de "
                    f"{base_cad:.0f}. Você ficou pesado na marcha: mais força por pedalada, mais desgaste "
                    f"muscular e mais carga no joelho para andar o mesmo tanto.",
                }
            )
        elif delta >= 8:
            reasons.append(
                {
                    "kind": "cadência",
                    "positive": True,
                    "impact": delta,
                    "text": f"Girou mais leve aqui: {cad:.0f} rpm contra {base_cad:.0f} do seu padrão. "
                    f"Cadência alta joga o esforço para o sistema cardiovascular e poupa a perna.",
                }
            )
        elif segment["terrain"] == "subida" and abs(delta) < 5:
            reasons.append(
                {
                    "kind": "cadência",
                    "positive": True,
                    "impact": 6,
                    "text": f"Cadência manteve {cad:.0f} rpm mesmo com {segment['gradient']:.1f}% de inclinação. "
                    f"Segurar o giro na subida é sinal de marcha bem escolhida.",
                }
            )

    hr = segment.get("avg_hr")
    power = segment.get("avg_power")
    base_hr = baseline.get("hr")
    base_power = baseline.get("power")
    if hr and base_hr:
        hr_delta = hr - base_hr
        if power and base_power:
            power_delta_pct = (power - base_power) / base_power * 100
            if hr_delta > 4 and power_delta_pct < -5:
                reasons.append(
                    {
                        "kind": "eficiência",
                        "positive": False,
                        "impact": abs(power_delta_pct) + hr_delta,
                        "text": f"Coração a {hr:.0f} bpm ({hr_delta:+.0f} do normal) entregando só {power:.0f} W "
                        f"({power_delta_pct:.0f}%). Mais custo por menos resultado: é a assinatura de fadiga, "
                        f"calor ou desidratação.",
                    }
                )
            elif hr_delta < -3 and power_delta_pct > 5:
                reasons.append(
                    {
                        "kind": "eficiência",
                        "positive": True,
                        "impact": power_delta_pct + abs(hr_delta),
                        "text": f"{power:.0f} W a apenas {hr:.0f} bpm: {power / hr:.2f} W por batimento, seu melhor "
                        f"rendimento do pedal. O motor estava barato aqui.",
                    }
                )
            elif power_delta_pct > 12:
                reasons.append(
                    {
                        "kind": "potência",
                        "positive": True,
                        "impact": power_delta_pct,
                        "text": f"Potência {power_delta_pct:.0f}% acima da média do treino ({power:.0f} W contra "
                        f"{base_power:.0f} W).",
                    }
                )
            elif power_delta_pct < -12:
                reasons.append(
                    {
                        "kind": "potência",
                        "positive": False,
                        "impact": abs(power_delta_pct),
                        "text": f"Potência {abs(power_delta_pct):.0f}% abaixo da média ({power:.0f} W contra "
                        f"{base_power:.0f} W).",
                    }
                )
        elif hr_delta > 6:
            reasons.append(
                {
                    "kind": "esforço",
                    "positive": False,
                    "impact": hr_delta,
                    "text": f"FC {hr:.0f} bpm, {hr_delta:.0f} acima da média do pedal. Custou caro.",
                }
            )

    vi = segment.get("variability")
    if vi and vi > 1.15:
        reasons.append(
            {
                "kind": "ritmo",
                "positive": False,
                "impact": (vi - 1) * 60,
                "text": f"Ritmo picado: variabilidade {vi:.2f}. Você alternou socos e alívios em vez de manter "
                f"pressão constante, e isso queima glicogênio mais rápido do que o ritmo médio sugere.",
            }
        )
    elif vi and vi < 1.06 and is_best:
        reasons.append(
            {
                "kind": "ritmo",
                "positive": True,
                "impact": 10,
                "text": f"Potência lisa, variabilidade {vi:.2f}. Ritmo constante é o jeito mais barato de "
                f"atravessar um trecho.",
            }
        )

    coasting = segment.get("coasting_ratio") or 0
    if coasting > 0.15 and segment["terrain"] != "descida":
        reasons.append(
            {
                "kind": "barriga",
                "positive": False,
                "impact": coasting * 100,
                "text": f"{coasting * 100:.0f}% do trecho sem pedalar, em terreno que não era descida. "
                f"Cada segundo de barriga em plano é velocidade que você devolve de graça.",
            }
        )

    if segment["terrain"] == "subida" and segment.get("vam"):
        base_vam = baseline.get("vam")
        if base_vam and base_vam > 0:
            vam_delta = (segment["vam"] - base_vam) / base_vam * 100
            if abs(vam_delta) > 10:
                direction = "acima" if vam_delta > 0 else "abaixo"
                reasons.append(
                    {
                        "kind": "subida",
                        "positive": vam_delta > 0,
                        "impact": abs(vam_delta),
                        "text": f"VAM de {segment['vam']:.0f} m/h, {abs(vam_delta):.0f}% {direction} das suas "
                        f"outras subidas do dia (inclinação média de {segment['gradient']:.1f}%).",
                    }
                )

    if not is_best and ride_position > 0.7 and baseline.get("decoupling", 0) > 5:
        reasons.append(
            {
                "kind": "fadiga",
                "positive": False,
                "impact": baseline["decoupling"],
                "text": f"Aconteceu nos últimos 30% do pedal, quando sua eficiência já tinha caído "
                f"{baseline['decoupling']:.0f}% em relação ao início. Boa parte disso é cansaço acumulado, "
                f"não o trecho em si.",
            }
        )

    torque = segment.get("torque_nm")
    if torque and cad and cad < 65 and torque > 45:
        reasons.append(
            {
                "kind": "torque",
                "positive": False,
                "impact": torque / 2,
                "text": f"Torque de {torque:.0f} Nm a {cad:.0f} rpm. Força alta com giro baixo é o padrão que mais "
                f"castiga joelho ao longo das semanas.",
            }
        )

    speed = segment.get("avg_speed_kmh")
    base_speed = baseline.get("speed")
    if speed and base_speed:
        speed_delta = (speed - base_speed) / base_speed * 100
        if abs(speed_delta) > 10:
            reasons.append(
                {
                    "kind": "velocidade",
                    "positive": speed_delta > 0,
                    "impact": abs(speed_delta),
                    "text": f"Velocidade média de {speed:.1f} km/h, {abs(speed_delta):.0f}% "
                    f"{'acima' if speed_delta > 0 else 'abaixo'} da média do pedal.",
                }
            )

    # Um trecho bom nao e explicado por defeitos, e um trecho ruim nao e explicado
    # por qualidades. Misturar as duas coisas foi o erro que essa filtragem corrige:
    # dizer "seu melhor momento foi porque voce ficou 17% sem pedalar" nao explica
    # nada, so faz o sistema parecer que nao entendeu a propria conta.
    matching = [r for r in reasons if r.get("positive") is is_best]
    matching.sort(key=lambda r: r["impact"], reverse=True)

    if not matching:
        terrain = segment["terrain"]
        matching = [
            {
                "kind": "resumo",
                "positive": is_best,
                "impact": 0,
                "text": (
                    f"Trecho de {segment['distance_m']:.0f} m em {terrain}, percorrido a "
                    f"{segment.get('avg_speed_kmh') or 0:.1f} km/h. Os indicadores desse trecho ficaram "
                    f"perto da sua média do dia, sem um fator isolado que explique a diferença."
                ),
            }
        ]
    return matching[:3]


# --------------------------------------------------------------------------
# Analise completa
# --------------------------------------------------------------------------


def analyze(streams: dict, ftp: int, sample_rate_s: float | None = None) -> dict:
    time_s = _arr(streams.get("t"), len(streams.get("t") or []))
    n = time_s.size
    if n < 60:
        return {"available": False, "reason": "Treino curto demais para analisar por trechos."}

    # Sem isso, todo tempo reportado sai dividido pela taxa real de gravacao.
    if sample_rate_s is None:
        sample_rate_s = effective_sample_rate(time_s)

    distance_km = _arr(streams.get("distance"), n)
    altitude = _arr(streams.get("altitude"), n)
    speed = _arr(streams.get("speed"), n)
    hr = _arr(streams.get("hr"), n)
    power = _arr(streams.get("power"), n)
    cadence = _arr(streams.get("cadence"), n)
    lat = _arr(streams.get("lat"), n)
    lon = _arr(streams.get("lon"), n)

    raw_segments = detect_segments(distance_km, altitude, time_s, sample_rate_s)
    segments = [
        segment_metrics(seg, time_s, distance_km, altitude, speed, hr, power, cadence, lat, lon)
        for seg in raw_segments
    ]

    # Linha de base do proprio treino. Comparar voce com voce mesmo, no mesmo dia,
    # com o mesmo vento e a mesma perna - e a comparacao mais justa que existe.
    baseline = {
        "power": _mean(power),
        "hr": _mean(hr),
        "cadence": float(np.mean(cadence[(~np.isnan(cadence)) & (cadence >= 5)]))
        if cadence[(~np.isnan(cadence)) & (cadence >= 5)].size
        else None,
        "speed": _mean(speed),
        "decoupling": aerobic_decoupling(power, hr, speed),
    }
    climbs = [s for s in segments if s["terrain"] == "subida" and s.get("vam")]
    baseline["vam"] = float(np.mean([s["vam"] for s in climbs])) if climbs else None

    has_hr = not np.all(np.isnan(hr))
    has_power = not np.all(np.isnan(power))
    if has_power and has_hr:
        basis = "watt por batimento"
    elif has_hr:
        basis = "velocidade corrigida pela inclinação, por batimento"
    else:
        basis = "potência (resultado, sem medida de custo)"

    # Quem pode disputar melhor/pior: trecho longo o suficiente, pedalado de
    # verdade e nao descida - descida mede a estrada, nao a perna.
    candidates = []
    for seg in segments:
        eff = efficiency(seg)
        if (
            eff is not None
            and seg["duration_s"] >= MIN_SEGMENT_S
            and seg["distance_m"] >= MIN_SEGMENT_M
            and seg["coasting_ratio"] <= MAX_COASTING_RATIO
            and seg["terrain"] != "descida"
        ):
            candidates.append({**seg, "efficiency": round(eff, 3)})

    highlights: dict = {"best": None, "worst": None}
    if len(candidates) >= 2:
        median_eff = float(np.median([c["efficiency"] for c in candidates]))
        for c in candidates:
            c["score"] = round(c["efficiency"] / median_eff * 100, 1) if median_eff else 100.0

        best = max(candidates, key=lambda c: c["score"])
        worst = min(candidates, key=lambda c: c["score"])
        total_time = float(time_s[-1]) or 1

        highlights["best"] = {
            **best,
            "verdict": f"{best['score'] - 100:+.0f}% de rendimento em relação ao seu padrão do dia",
            "reasons": explain(best, baseline, best["start_index"] / n, True),
        }
        highlights["worst"] = {
            **worst,
            "verdict": f"{worst['score'] - 100:+.0f}% de rendimento em relação ao seu padrão do dia",
            "reasons": explain(worst, baseline, worst["end_index"] / n, False),
        }
        highlights["ranking"] = sorted(candidates, key=lambda c: c["score"], reverse=True)
        _ = total_time

    return {
        "available": True,
        "basis": basis,
        "has_hr": bool(has_hr),
        "segments": segments,
        "highlights": highlights,
        "baseline": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in baseline.items()},
        "cadence": cadence_report(cadence, power, speed, altitude, distance_km, segments, sample_rate_s, ftp),
        "gears": gear_report(cadence, speed, sample_rate_s),
        "splits": kilometre_splits(distance_km, time_s, altitude, hr, power, cadence),
        "pacing": pacing_report(time_s, power, speed, hr),
    }


def aerobic_decoupling(power: np.ndarray, hr: np.ndarray, speed: np.ndarray) -> float:
    """Quanto a eficiencia caiu da primeira para a segunda metade, em %.

    Acima de 5% costuma indicar que o treino foi longo demais para a base atual,
    ou que faltou hidratacao/comida. E um dos indicadores mais uteis que existem
    e quase ninguem olha.
    """
    output = power if not np.all(np.isnan(power)) else speed
    if np.all(np.isnan(output)) or np.all(np.isnan(hr)):
        return 0.0
    half = output.size // 2
    if half < 60:
        return 0.0

    def ratio(o, h):
        o_mean = _mean(o)
        h_mean = _mean(h)
        return o_mean / h_mean if o_mean and h_mean else None

    first = ratio(output[:half], hr[:half])
    second = ratio(output[half:], hr[half:])
    if not first or not second:
        return 0.0
    return round((first - second) / first * 100, 1)


def cadence_report(
    cadence: np.ndarray,
    power: np.ndarray,
    speed: np.ndarray,
    altitude: np.ndarray,
    distance_km: np.ndarray,
    segments: list[dict],
    sample_rate_s: float,
    ftp: int,
) -> dict:
    clean = cadence[~np.isnan(cadence)]
    if clean.size == 0:
        return {"available": False}

    pedalling = clean[clean >= 5]
    coasting_s = float(np.sum(clean < 5) * sample_rate_s)

    bands = []
    for label, low, high in CADENCE_BANDS:
        seconds = float(np.sum((pedalling >= low) & (pedalling < high)) * sample_rate_s)
        bands.append({"band": label, "seconds": round(seconds), "rpm_low": low})

    by_terrain = {}
    for terrain in ("subida", "plano", "descida"):
        values = []
        for seg in segments:
            if seg["terrain"] == terrain and seg.get("avg_cadence"):
                values.append(seg["avg_cadence"])
        if values:
            by_terrain[terrain] = round(float(np.mean(values)), 0)

    # "Mashing": empurrar marcha pesada com forca alta. Eficiente no curto prazo,
    # caro no joelho e no glicogenio no longo.
    mashing_s = 0.0
    if not np.all(np.isnan(power)):
        mask = (cadence < 70) & (cadence >= 5) & (power > 0.75 * ftp)
        mashing_s = float(np.sum(mask) * sample_rate_s)

    avg_cadence = float(np.mean(pedalling)) if pedalling.size else None
    avg_power = _mean(power)
    torque = None
    if avg_power and avg_cadence and avg_cadence > 5:
        torque = round(avg_power / (2 * np.pi * avg_cadence / 60), 1)

    insight = None
    if avg_cadence:
        if avg_cadence < 72:
            insight = (
                f"Seu giro médio está em {avg_cadence:.0f} rpm. Cadência nessa faixa carrega mais a perna e "
                f"menos o pulmão, e ao longo das semanas costuma cobrar do joelho. Vale experimentar subir "
                f"uma coroa e treinar em 85 a 90 rpm em pedais leves até ficar natural."
            )
        elif avg_cadence > 95:
            insight = (
                f"Giro médio de {avg_cadence:.0f} rpm, bem alto. Poupa a perna, mas cobra do cardiovascular. "
                f"Se sua FC média está alta para o esforço, pesar um pouco a marcha pode baixar o custo."
            )
        else:
            insight = (
                f"Giro médio de {avg_cadence:.0f} rpm, dentro da faixa que a maioria dos ciclistas sustenta "
                f"com melhor economia."
            )
    if mashing_s > 180:
        insight = (insight or "") + (
            f" Atenção: {mashing_s / 60:.0f} min pedalando abaixo de 70 rpm com potência alta. "
            f"É o padrão de carga que mais castiga a articulação."
        )

    return {
        "available": True,
        "avg_rpm": round(avg_cadence, 0) if avg_cadence else None,
        "bands": bands,
        "by_terrain": by_terrain,
        "coasting_s": round(coasting_s),
        "mashing_s": round(mashing_s),
        "avg_torque_nm": torque,
        "insight": insight,
    }


def kilometre_splits(
    distance_km: np.ndarray,
    time_s: np.ndarray,
    altitude: np.ndarray,
    hr: np.ndarray,
    power: np.ndarray,
    cadence: np.ndarray,
) -> list[dict]:
    """Parciais por quilometro, igual a tabela de voltas de uma corrida."""
    total = float(np.nanmax(distance_km)) if not np.all(np.isnan(distance_km)) else 0
    if total < 1:
        return []

    splits = []
    for km in range(int(total)):
        mask = (distance_km >= km) & (distance_km < km + 1)
        idx = np.where(mask)[0]
        if idx.size < 2:
            continue
        a, b = idx[0], idx[-1]
        duration = float(time_s[b] - time_s[a])
        if duration <= 0:
            continue
        seg_alt = altitude[a : b + 1]
        clean_alt = seg_alt[~np.isnan(seg_alt)]
        gain = float(np.diff(clean_alt)[np.diff(clean_alt) > 0].sum()) if clean_alt.size > 1 else 0.0
        splits.append(
            {
                "km": km + 1,
                "duration_s": round(duration),
                "speed_kmh": round(3600 / duration, 1),
                "elevation_m": round(gain),
                "avg_hr": round(_mean(hr[a : b + 1]) or 0) or None,
                "avg_power": round(_mean(power[a : b + 1]) or 0) or None,
                "avg_cadence": round(_mean(cadence[a : b + 1]) or 0) or None,
            }
        )
    return splits


def pacing_report(time_s: np.ndarray, power: np.ndarray, speed: np.ndarray, hr: np.ndarray) -> dict:
    """Como voce distribuiu o esforco: comecou forte e apagou, ou fechou melhor?"""
    output = power if not np.all(np.isnan(power)) else speed
    if np.all(np.isnan(output)):
        return {"available": False}

    quarters = np.array_split(output, 4)
    values = [_mean(q) for q in quarters]
    if any(v is None for v in values):
        return {"available": False}

    first, last = values[0], values[-1]
    change = (last - first) / first * 100 if first else 0
    if change < -8:
        verdict = (
            f"Split positivo: você fechou {abs(change):.0f}% mais fraco do que começou. Sair mais contido nos "
            f"primeiros 20 minutos costuma render um tempo total melhor."
        )
    elif change > 8:
        verdict = f"Split negativo: fechou {change:.0f}% mais forte do que começou. Distribuição de esforço bem feita."
    else:
        verdict = f"Ritmo parelho do início ao fim (variação de {change:+.0f}%). Boa gestão de esforço."

    return {
        "available": True,
        "quarters": [round(v, 1) for v in values],
        "change_pct": round(change, 1),
        "verdict": verdict,
        "unit": "W" if not np.all(np.isnan(power)) else "km/h",
    }


# --------------------------------------------------------------------------
# Marchas: o que velocidade + cadencia revelam sem nenhum sensor a mais
# --------------------------------------------------------------------------


def gear_report(cadence: np.ndarray, speed: np.ndarray, sample_rate_s: float = 1.0) -> dict:
    """Descobre em que marchas voce andou, so com velocidade e cadencia.

    A conta e direta: velocidade dividida pela cadencia da o *desenvolvimento* -
    quantos metros a bike anda a cada volta completa do pedal. Cada combinacao de
    coroa e coroa traseira tem um desenvolvimento proprio, entao os picos dessa
    distribuicao sao as marchas que voce realmente usa.

    Serve para responder uma pergunta que ninguem consegue responder olhando o
    ciclocomputador: voce esta trocando marcha, ou anda o pedal inteiro em duas ou
    tres relacoes e compensa com a perna?
    """
    valid = (~np.isnan(cadence)) & (~np.isnan(speed)) & (cadence >= 30) & (speed > 4)
    if np.sum(valid) < 60:
        return {"available": False}

    rpm = cadence[valid]
    kmh = speed[valid]
    # Formula canonica mora no drivetrain: e conta de maquina, nao de pedal.
    development = drivetrain.development(rpm, kmh)
    development = development[(development > 1.5) & (development < 12)]
    if development.size < 60:
        return {"available": False}

    # Histograma fino: cada marcha aparece como um pico proprio.
    hist, edges = np.histogram(development, bins=40, range=(1.5, 11.5))
    centres = (edges[:-1] + edges[1:]) / 2
    total = hist.sum()

    peaks = []
    for i in range(1, len(hist) - 1):
        share = hist[i] / total
        if share > 0.05 and hist[i] >= hist[i - 1] and hist[i] >= hist[i + 1]:
            peaks.append({"development_m": round(float(centres[i]), 2), "share": round(float(share), 3)})
    peaks.sort(key=lambda p: p["share"], reverse=True)

    top_three = sum(p["share"] for p in peaks[:3])
    spread = float(np.percentile(development, 90) - np.percentile(development, 10))

    if top_three > 0.6:
        insight = (
            f"Você passou {top_three * 100:.0f}% do pedal em apenas três relações. Trocar marcha mais cedo, "
            f"antes da rampa mudar, costuma segurar a cadência estável e cansar menos a perna."
        )
    elif spread < 2.0:
        insight = (
            f"Sua faixa de marchas usada é estreita: quase tudo entre {np.percentile(development, 10):.1f} e "
            f"{np.percentile(development, 90):.1f} m por pedalada. Vale explorar as relações das pontas."
        )
    else:
        insight = (
            f"Boa distribuição de marchas: você transitou entre {np.percentile(development, 10):.1f} e "
            f"{np.percentile(development, 90):.1f} m por pedalada, sinal de que está acompanhando o terreno."
        )

    return {
        "available": True,
        "histogram": [
            {"development_m": round(float(c), 2), "seconds": round(float(h) * sample_rate_s)}
            for c, h in zip(centres, hist)
            if h > 0
        ],
        "gears_used": peaks[:6],
        "median_development_m": round(float(np.median(development)), 2),
        "spread_m": round(spread, 2),
        "insight": insight,
    }
