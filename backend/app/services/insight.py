"""Insight do Treinador: agrega os treinos recentes em quatro dimensoes
(cadencia, pacing, zonas, terreno) e pede ao Ollama um comentario acionavel.

Divisao de trabalho de proposito: os NUMEROS saem daqui, em Python, e alimentam
os graficos - deterministicos, sempre presentes. O TEXTO vem do LLM e e
best-effort: se o Ollama estiver fora, a tela ainda mostra os graficos.

Voz (definida com o usuario): pode prescrever acoes de melhoria e evolucao,
inclusive tecnica e intensidade, SEMPRE para frente. Nunca cobra o passado -
nada de "voce deveria ter", "faltou", "preguica", "vergonha".
"""

from __future__ import annotations

import json
import re

import httpx
import numpy as np

from . import metrics
from .analysis import effective_sample_rate

# Faixas de cadencia (rpm) que a interface e o texto usam.
CADENCE_BANDS = [
    ("Pesada (<60)", 0, 60),
    ("Média (60-75)", 60, 75),
    ("Ideal (75-90)", 75, 90),
    ("Alta (90+)", 90, 999),
]


def _arr(stream: list | None) -> np.ndarray:
    if not stream:
        return np.array([], dtype=float)
    return np.array([np.nan if v is None else float(v) for v in stream], dtype=float)


def _quarters(values: np.ndarray) -> list[float | None]:
    """Media de cada quarto do treino - revela se o esforco cai no fim."""
    clean = values[~np.isnan(values)]
    if clean.size < 4:
        return [None, None, None, None]
    parts = np.array_split(values, 4)
    out = []
    for p in parts:
        p = p[~np.isnan(p)]
        out.append(round(float(np.mean(p)), 1) if p.size else None)
    return out


def _ride_dimensions(payload: dict, ftp: int) -> dict | None:
    t = _arr(payload.get("t"))
    if t.size < 60:
        return None
    sr = effective_sample_rate(t)

    cadence = _arr(payload.get("cadence"))
    power = _arr(payload.get("power"))
    altitude = _arr(payload.get("altitude"))
    distance = _arr(payload.get("distance"))  # km acumulado

    # Cadencia: segundos por faixa, so pedalando (>= 5 rpm).
    cad_seconds = {name: 0.0 for name, _, _ in CADENCE_BANDS}
    pedalling = cadence[(~np.isnan(cadence)) & (cadence >= 5)]
    for name, low, high in CADENCE_BANDS:
        cad_seconds[name] = round(int(np.sum((pedalling >= low) & (pedalling < high))) * sr, 1)
    avg_cadence = round(float(np.mean(pedalling)), 0) if pedalling.size else None

    # Zonas de potencia (segundos). Potencia estimada - ler como tendencia.
    zones = metrics.time_in_zones(payload.get("power"), metrics.POWER_ZONES, ftp, sr)

    # Pacing: media de potencia por quarto do treino.
    quarters = _quarters(power)

    # Terreno: segundos em subida/plano/descida a partir da inclinacao ponto a ponto.
    terr = {"subida": 0.0, "plano": 0.0, "descida": 0.0}
    if altitude.size == distance.size and altitude.size > 1:
        d_m = distance * 1000.0
        dd = np.diff(d_m)
        dh = np.diff(altitude)
        with np.errstate(divide="ignore", invalid="ignore"):
            grade = np.where(dd > 0.5, dh / dd * 100.0, np.nan)
        for g in grade:
            if np.isnan(g):
                continue
            key = "subida" if g > 1.5 else "descida" if g < -1.5 else "plano"
            terr[key] += sr

    return {
        "cadence_seconds": cad_seconds,
        "avg_cadence": avg_cadence,
        "zone_seconds": zones,
        "quarters_power": quarters,
        "terrain_seconds": {k: round(v, 1) for k, v in terr.items()},
    }


def build_summary(rides: list[dict], ftp: int) -> dict:
    """rides: [{date, title, minutes, distance_km, np, tss, vi, avg_cadence,
    power_is_estimated, payload}]. Agrega as quatro dimensoes."""
    dims = []
    for r in rides:
        d = _ride_dimensions(r.get("payload") or {}, ftp)
        if d:
            dims.append(d)

    def _sum_dict(key: str) -> dict:
        out: dict[str, float] = {}
        for d in dims:
            for k, v in d[key].items():
                out[k] = round(out.get(k, 0.0) + (v or 0.0), 1)
        return out

    cadence_seconds = _sum_dict("cadence_seconds")
    zone_seconds = _sum_dict("zone_seconds")
    terrain_seconds = _sum_dict("terrain_seconds")

    # Pacing medio: media dos quartos entre os treinos que tem potencia.
    q_stack = [d["quarters_power"] for d in dims if all(q is not None for q in d["quarters_power"])]
    quarters = None
    fade_pct = None
    if q_stack:
        quarters = [round(float(np.mean([q[i] for q in q_stack])), 1) for i in range(4)]
        if quarters[0]:
            fade_pct = round((quarters[3] - quarters[0]) / quarters[0] * 100.0, 1)

    cad_total = sum(cadence_seconds.values()) or 1
    heavy_share = round((cadence_seconds.get("Pesada (<60)", 0) + cadence_seconds.get("Média (60-75)", 0)) / cad_total * 100)
    avg_cad = [d["avg_cadence"] for d in dims if d["avg_cadence"]]

    return {
        "rides_analyzed": len(dims),
        "cadence": {
            "seconds": cadence_seconds,
            "avg_rpm": round(float(np.mean(avg_cad))) if avg_cad else None,
            "heavy_share_pct": heavy_share,
        },
        "zones": {"seconds": zone_seconds},
        "pacing": {"quarters_power": quarters, "fade_pct": fade_pct},
        "terrain": {"seconds": terrain_seconds},
        "power_estimated": any(r.get("power_is_estimated") for r in rides),
        "totals": {
            "minutes": round(sum(r.get("minutes", 0) for r in rides)),
            "distance_km": round(sum(r.get("distance_km", 0) for r in rides), 1),
            "avg_vi": round(float(np.mean([r["vi"] for r in rides if r.get("vi")])), 2)
            if any(r.get("vi") for r in rides)
            else None,
        },
    }


# --- parte do LLM ---------------------------------------------------------

SYSTEM_PROMPT = """Você é o Treinador de um app de ciclismo, escrevendo em português do Brasil.

Tom: caloroso, direto, editorial. Fala com o ciclista por "você".

ORTOGRAFIA: escreva em português do Brasil impecável, com toda a acentuação e cedilha corretas — por exemplo "potência", "cadência", "distribuição", "esforço", "você", "é", "análise", "até", "número". Nunca escreva uma palavra sem o acento que ela tem.

O que você PODE fazer:
- Apontar pontos a melhorar e sugerir ações concretas de evolução, inclusive de técnica e de intensidade (ex.: girar mais leve, incluir blocos mais fortes, distribuir o esforço).
- Sempre olhando para a frente: "para evoluir, experimente...", "o próximo passo é...".

O que você NUNCA faz:
- Cobrar ou culpar o passado. Proibido: "você deveria ter", "faltou", "preguiça", "vergonha", qualquer tom de bronca.
- Inventar número que não está nos dados. Use só o que foi dado.

Contexto do app: o ciclista não tem potenciômetro, então a potência é ESTIMADA — trate como tendência, nunca valor absoluto nem comparável com outra pessoa.

Responda APENAS um JSON válido, sem markdown, com exatamente estas chaves (cada valor 1 a 2 frases, concreto e específico aos números):
{"overall": "...", "cadencia": "...", "pacing": "...", "zonas": "...", "terreno": "..."}"""


def _fmt_minutes(seconds_map: dict) -> str:
    return ", ".join(f"{k}: {round(v/60)} min" for k, v in seconds_map.items() if v)


def _user_prompt(s: dict) -> str:
    cad = s["cadence"]
    pac = s["pacing"]
    q = pac["quarters_power"] or ["?", "?", "?", "?"]
    linhas = [
        f"Treinos analisados: {s['rides_analyzed']} | volume {s['totals']['minutes']} min, {s['totals']['distance_km']} km.",
        f"Cadência média: {cad['avg_rpm']} rpm. Tempo por faixa -> {_fmt_minutes(cad['seconds'])}. "
        f"{cad['heavy_share_pct']}% do tempo pedalado foi em giro baixo (marcha pesada).",
        f"Zonas de potência (estimada) -> {_fmt_minutes(s['zones']['seconds'])}.",
        f"Ritmo ao longo do MESMO pedal (potência média, do começo ao fim, sem relação "
        f"com número de treinos): começo {q[0]} W, depois {q[1]} W, em seguida {q[2]} W, "
        f"e no fim {q[3]} W (do começo ao fim: {pac['fade_pct']}%; negativo = perde força no fim do pedal).",
        f"Terreno -> {_fmt_minutes(s['terrain']['seconds'])}.",
        f"Índice de variabilidade médio: {s['totals']['avg_vi']} (perto de 1.0 é constante; alto é picado).",
    ]
    return "\n".join(linhas)


def _strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _extract_json(text: str) -> dict | None:
    text = _strip_think(text)
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _extract_json_array(text: str) -> list | None:
    text = _strip_think(text)
    m = re.search(r"\[.*\]", text, flags=re.DOTALL)
    if not m:
        return None
    try:
        val = json.loads(m.group(0))
        return val if isinstance(val, list) else None
    except json.JSONDecodeError:
        return None


# Exemplo few-shot: o qwen3 tende a comer acentos; espelhar uma resposta ja
# acentuada e o que efetivamente faz ele escrever portugues correto. Os numeros
# aqui sao ficticios, so para ancorar o ESTILO e a acentuacao - nao o conteudo.
EXAMPLE_USER = (
    "Treinos analisados: 2 | volume 90 min, 28 km.\n"
    "Cadência média: 82 rpm. 30% do tempo em giro baixo.\n"
    "Ritmo: começo 150 W, fim 140 W (-7%)."
)
EXAMPLE_ASSISTANT = json.dumps(
    {
        "overall": "Você vem mantendo uma boa constância e um ritmo equilibrado ao longo dos pedais. Para evoluir, o próximo passo é variar um pouco a intensidade.",
        "cadencia": "Sua cadência está num patamar saudável; para ganhar eficiência, experimente segurar o giro acima de 85 rpm nas retas.",
        "pacing": "A potência caiu pouco do começo ao fim, sinal de bom controle de esforço. Dá para ousar um final um pouco mais forte.",
        "zonas": "Você distribuiu bem o esforço. Incluir blocos curtos mais intensos ajudaria a elevar o teto aeróbico.",
        "terreno": "O terreno foi variado. Buscar subidas um pouco mais longas acrescenta força específica.",
    },
    ensure_ascii=False,
)


# O qwen3 compoe o texto comendo acentos, mas ACERTA quando a tarefa e so
# corrigir (quase um echo). Entao geramos o conteudo e passamos por um segundo
# passe que apenas acrescenta acentos/cedilha - sem reescrever nada.
CORRECTION_SYSTEM = (
    "Você corrige a acentuação do português do Brasil. Para cada linha recebida, "
    "devolva a MESMA linha - mesmas palavras, mesma ordem, mesmo marcador inicial "
    "[[N]] - apenas acrescentando os acentos, o til e a cedilha que faltam, e usando "
    "vírgula como separador decimal. Não reescreva, não resuma, não remova nada. "
    "Responda só as linhas corrigidas."
)


def _fix_accents(texts: list[str], host: str, model: str, timeout: float = 120.0) -> list[str]:
    marcado = "\n".join(f"[[{i}]] {t}" for i, t in enumerate(texts))
    try:
        resp = httpx.post(
            f"{host.rstrip('/')}/api/chat",
            json={
                "model": model,
                "stream": False,
                "think": False,
                "options": {"temperature": 0},
                "messages": [
                    {"role": "system", "content": CORRECTION_SYSTEM},
                    {"role": "user", "content": marcado},
                ],
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        content = _strip_think(resp.json().get("message", {}).get("content", ""))
    except (httpx.HTTPError, ValueError):
        return texts

    out = list(texts)
    for i in range(len(texts)):
        m = re.search(rf"\[\[{i}\]\]\s*(.*?)(?=\[\[{i + 1}\]\]|$)", content, flags=re.DOTALL)
        if m and m.group(1).strip():
            out[i] = m.group(1).strip()
    return out


def generate_text(summary: dict, host: str, model: str, timeout: float = 180.0) -> dict | None:
    """Chama o Ollama. Devolve o dict de comentarios, ou None se algo falhar."""
    try:
        resp = httpx.post(
            f"{host.rstrip('/')}/api/chat",
            json={
                "model": model,
                "stream": False,
                "think": False,
                "options": {"temperature": 0.4},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": EXAMPLE_USER},
                    {"role": "assistant", "content": EXAMPLE_ASSISTANT},
                    {"role": "user", "content": _user_prompt(summary)},
                ],
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "")
    except (httpx.HTTPError, ValueError):
        return None

    data = _extract_json(content)
    if not isinstance(data, dict):
        return None
    keys = ("overall", "cadencia", "pacing", "zonas", "terreno")
    valores = [str(data.get(k, "")).strip() for k in keys]
    valores = _fix_accents(valores, host, model)  # segundo passe: so acentuacao
    return dict(zip(keys, valores))


# --- guia detalhado (tela "Tecnica" / Pontos de evolucao) -----------------

GUIDE_SYSTEM = """Você é o Treinador de um app de ciclismo, escrevendo em português do Brasil.

Tom: caloroso, direto, editorial. Fala com o ciclista por "você".

ORTOGRAFIA: português do Brasil impecável, com toda a acentuação e cedilha corretas.

Para cada dimensão (cadência, pacing, zonas, terreno), escreva um guia em TRÊS partes:
- "mostra": o que o gráfico daquele tópico revela, específico aos números (1 frase).
- "melhorar": o que fazer para evoluir nesse ponto. Pode prescrever técnica e intensidade, sempre para frente (1 a 2 frases).
- "treino": como aplicar no PRÓXIMO pedal — um exercício prático e executável, com números (ex.: "em 3 blocos de 5 min, segure a cadência acima de 85 rpm; descanse 3 min entre eles").

E um "intro": 1 a 2 frases ligando o conjunto.

NUNCA cobre nem culpe o passado (nada de "você deveria ter", "faltou", "preguiça", "vergonha"). Não invente número fora dos dados. A potência é ESTIMADA (sem potenciômetro) — trate como tendência.

Responda APENAS um JSON válido, sem markdown, exatamente com esta forma:
{"intro":"...","cadencia":{"mostra":"...","melhorar":"...","treino":"..."},"pacing":{"mostra":"...","melhorar":"...","treino":"..."},"zonas":{"mostra":"...","melhorar":"...","treino":"..."},"terreno":{"mostra":"...","melhorar":"...","treino":"..."}}"""

GUIDE_DIMS = ("cadencia", "pacing", "zonas", "terreno")
GUIDE_PARTS = ("mostra", "melhorar", "treino")


def generate_guide(summary: dict, host: str, model: str, timeout: float = 240.0) -> dict | None:
    """Guia detalhado em 3 partes por dimensao. Mesmo tom e mesmo segundo passe
    de acentuacao do generate_text."""
    try:
        resp = httpx.post(
            f"{host.rstrip('/')}/api/chat",
            json={
                "model": model,
                "stream": False,
                "think": False,
                "options": {"temperature": 0.4},
                "messages": [
                    {"role": "system", "content": GUIDE_SYSTEM},
                    {"role": "user", "content": _user_prompt(summary)},
                ],
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "")
    except (httpx.HTTPError, ValueError):
        return None

    data = _extract_json(content)
    if not isinstance(data, dict):
        return None

    # Achata todas as frases numa lista, corrige a acentuacao de uma vez, remonta.
    flat: list[str] = [str(data.get("intro", "")).strip()]
    for d in GUIDE_DIMS:
        bloco = data.get(d) or {}
        for p in GUIDE_PARTS:
            flat.append(str(bloco.get(p, "")).strip() if isinstance(bloco, dict) else "")
    flat = _fix_accents(flat, host, model)

    out: dict = {"intro": flat[0]}
    i = 1
    for d in GUIDE_DIMS:
        out[d] = {p: flat[i + j] for j, p in enumerate(GUIDE_PARTS)}
        i += len(GUIDE_PARTS)
    return out


# --- dicas localizadas no percurso (tela Tecnica, mapa do treino) ----------

ROUTE_SYSTEM = """Você é o Treinador de um app de ciclismo, escrevendo em português do Brasil.

Para cada trecho de um pedal que te passo, escreva UMA dica curta e prática de como melhorar ALI no próximo pedal — pode ser técnica, postura, troca de marcha ou intensidade. Sempre para frente, concreta e específica aos números daquele trecho. Nunca cobre nem culpe o passado. Não invente número fora dos dados. A potência é ESTIMADA (sem potenciômetro).

Responda APENAS um array JSON de strings (uma dica por trecho), na MESMA ordem em que recebeu os trechos, sem nenhum outro texto. Cada dica tem 1 ou 2 frases."""


def _route_prompt(points: list[dict]) -> str:
    linhas = ["Trechos do pedal (em ordem):"]
    for i, p in enumerate(points, 1):
        linhas.append(
            f"{i}) {p.get('terrain', '?')} de {p.get('gradient', '?')}% entre km "
            f"{p.get('start_km', '?')} e {p.get('end_km', '?')}. "
            f"Cadência {p.get('avg_cadence')} rpm, torque {p.get('torque_nm')} Nm, "
            f"potência estimada {p.get('avg_power')} W. Observação: {p.get('problema', '')}"
        )
    return "\n".join(linhas)


def route_dicas(points: list[dict], host: str, model: str, timeout: float = 180.0) -> list[str]:
    """Uma dica por trecho, na ordem. Lista vazia/parcial se o Ollama falhar."""
    if not points:
        return []
    try:
        resp = httpx.post(
            f"{host.rstrip('/')}/api/chat",
            json={
                "model": model,
                "stream": False,
                "think": False,
                "options": {"temperature": 0.4},
                "messages": [
                    {"role": "system", "content": ROUTE_SYSTEM},
                    {"role": "user", "content": _route_prompt(points)},
                ],
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "")
    except (httpx.HTTPError, ValueError):
        return []

    arr = _extract_json_array(content)
    if not arr:
        return []
    dicas = [str(x).strip() for x in arr][: len(points)]
    return _fix_accents(dicas, host, model)
