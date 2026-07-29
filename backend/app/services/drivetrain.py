"""Matematica da transmissao: quais relacoes a bike TEM, e quais delas voce usou.

A fronteira com o analysis.py importa: este modulo fala da MAQUINA, o analysis
fala do PEDAL. Aqui nao entra treino, nem banco, nem I/O - so numero de dentes,
circunferencia e a conta que sai dai. Por isso da para testar sem nada montado.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import numpy as np

# Duas relacoes cujo desenvolvimento difere menos que isso sao indistinguiveis.
# A cadencia e gravada em rpm INTEIRO: a 70 rpm, 1 rpm ja e 1,4% de erro. A
# velocidade do sensor/GPS carrega mais 2 a 3%. Somando, qualquer diferenca
# abaixo de ~4% esta dentro do ruido, e afirmar qual das duas voce usou seria
# chute com cara de fato.
#
# O limiar e RELATIVO, nao absoluto, porque o erro e multiplicativo: 0,10 m e
# enorme numa marcha de 1,6 m e irrelevante numa de 6,9 m. Medido na ST100, um
# limiar fixo de 0,20 m junta 4 marchas num grupo so; 4% relativo resolve
# melhor embaixo sem superagrupar em cima.
COLLISION_PCT = 0.04

# Distancia maxima entre a amostra e o CENTRO da faixa para contar como uso.
# Relativa ao centro, nao a amostra: assim a largura da faixa e propriedade fixa
# da marcha e nao muda conforme o ruido de cada leitura.
ASSIGN_TOLERANCE_PCT = 0.05

# Faixa com menos que isso nao conta como usada. Passar por uma marcha durante
# a troca nao e ter usado a marcha.
UNUSED_THRESHOLD_S = 10

# Acima disso, o cassete ou o aro declarado provavelmente estao errados.
OFF_GEAR_WARN = 0.10

# Mesmo criterio do analysis.gear_report(), de proposito: abaixo disso a razao
# velocidade/cadencia vira ruido. As duas leituras precisam concordar sobre o
# que e uma amostra valida, senao os totais nao fecham entre uma tela e outra.
MIN_CADENCE_RPM = 30
MIN_SPEED_KMH = 4
MIN_SAMPLES = 60

# Faixa util de dentes: mesma que a API valida na entrada. Serve de rede de
# seguranca aqui dentro tambem, porque gear_table() e funcao publica que le
# dados ja gravados no banco - um cog 0 ou negativo la dentro nao pode virar
# ZeroDivisionError ou um desenvolvimento negativo estourando o endpoint.
MIN_CHAINRING_TEETH = 20
MAX_CHAINRING_TEETH = 60
MIN_COG_TEETH = 9
MAX_COG_TEETH = 52


@dataclass(frozen=True)
class Gear:
    """Uma combinacao mecanica: coroa x cog, e quanto ela anda por pedalada."""

    development_m: float
    chainring: int
    cog: int

    @property
    def name(self) -> str:
        return f"{self.chainring}x{self.cog}"


@dataclass(frozen=True)
class GearGroup:
    """Faixa de relacoes que a medicao nao consegue separar.

    Numa 3x quase metade das marchas e duplicata mecanica de outra: na ST100,
    24x24 e 34x34 dao EXATAMENTE o mesmo desenvolvimento. Velocidade dividida
    por cadencia nao tem como dizer em qual coroa voce estava.

    A ambiguidade atinge so a atribuicao de USO. Ela nao atinge a de NAO-USO: se
    a faixa ficou vazia, todas as relacoes dela ficaram paradas, sem duvida.
    Vazio e inequivoco - e por isso que "marchas nao usadas" e a leitura que a
    fisica permite fazer com precisao.
    """

    development_m: float  # centro da faixa: media do grupo
    gears: tuple[Gear, ...]

    @property
    def label(self) -> str:
        return " = ".join(g.name for g in self.gears)


def development(cadence: np.ndarray, speed_kmh: np.ndarray) -> np.ndarray:
    """Metros que a bike anda a cada volta completa do pedal.

    E a conta que revela a marcha sem nenhum sensor a mais. Casa canonica da
    formula: o analysis.gear_report() importa daqui em vez de manter copia.
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        return (speed_kmh / 3.6) * 60 / cadence


def gear_table(chainrings, cassette, wheel_mm) -> list[Gear]:
    """Todas as combinacoes mecanicas da bike, ordenadas por desenvolvimento.

    Dado invalido e ignorado, nao derruba a conta: esta funcao le direto do que
    foi salvo na bike, e um cog 0 ou negativo no banco nao pode virar
    ZeroDivisionError nem uma marcha de desenvolvimento negativo no meio da
    tabela que o endpoint de analise devolve pro usuario.
    """
    if not chainrings or not cassette or not wheel_mm:
        return []
    wheel_m = wheel_mm / 1000
    rings = [int(r) for r in chainrings if MIN_CHAINRING_TEETH <= int(r) <= MAX_CHAINRING_TEETH]
    cogs = [int(c) for c in cassette if MIN_COG_TEETH <= int(c) <= MAX_COG_TEETH]
    gears = [
        Gear(round(ring / cog * wheel_m, 4), ring, cog) for ring, cog in product(rings, cogs)
    ]
    return sorted(gears, key=lambda g: g.development_m)


def collapse(gears: list[Gear], tolerance_pct: float | None = None) -> list[GearGroup]:
    """Junta relacoes cujo desenvolvimento a medicao nao separa."""
    if tolerance_pct is None:
        tolerance_pct = COLLISION_PCT
    buckets: list[list[Gear]] = []
    for gear in gears:
        anterior = buckets[-1][-1].development_m if buckets else None
        if anterior is not None and gear.development_m - anterior < tolerance_pct * anterior:
            buckets[-1].append(gear)
        else:
            buckets.append([gear])
    return [
        GearGroup(
            round(sum(g.development_m for g in bucket) / len(bucket), 4),
            tuple(bucket),
        )
        for bucket in buckets
    ]


def _to_array(values) -> np.ndarray:
    if values is None:
        return np.array([], dtype=float)
    if isinstance(values, np.ndarray):
        return values.astype(float)
    return np.array([v if v is not None else np.nan for v in values], dtype=float)


def coverage(cadence, speed_kmh, groups: list[GearGroup], sample_rate_s: float) -> dict | None:
    """Quanto tempo o pedal passou em cada faixa de marcha, e o que ficou parado.

    O binning e POR MARCHA, nao por largura fixa. O histograma do gear_report usa
    40 faixas de 0,25 m, grosso demais: relacoes colidem a 0,03 m, quinze vezes
    menos que uma faixa. Aqui as faixas sao moldadas pelas marchas declaradas.

    A conversao de contagem para segundos usa a taxa REAL de amostragem. Assumir
    1 Hz dividiria todo tempo pelo fator de gravacao do aparelho (SPEC 3.10).
    """
    if not groups:
        return None

    cad = _to_array(cadence)
    spd = _to_array(speed_kmh)
    if cad.size == 0 or spd.size == 0:
        return None
    tamanho = min(cad.size, spd.size)
    cad, spd = cad[:tamanho], spd[:tamanho]

    valid = (
        (~np.isnan(cad)) & (~np.isnan(spd)) & (cad >= MIN_CADENCE_RPM) & (spd > MIN_SPEED_KMH)
    )
    if int(np.sum(valid)) < MIN_SAMPLES:
        return None

    dev = development(cad[valid], spd[valid])
    centres = np.array([g.development_m for g in groups])
    tolerancia = centres * ASSIGN_TOLERANCE_PCT

    distancias = np.abs(dev[:, None] - centres[None, :])
    mais_perto = distancias.argmin(axis=1)
    dentro = distancias[np.arange(dev.size), mais_perto] <= tolerancia[mais_perto]

    counts = np.bincount(mais_perto[dentro], minlength=len(groups))
    fora_s = float(np.sum(~dentro)) * sample_rate_s

    bands = []
    for group, count in zip(groups, counts):
        seconds = float(count) * sample_rate_s
        bands.append(
            {
                "development_m": group.development_m,
                "gears": [g.name for g in group.gears],
                "label": group.label,
                "seconds": round(seconds),
                "used": seconds >= UNUSED_THRESHOLD_S,
            }
        )

    total = sum(b["seconds"] for b in bands) + fora_s
    off_ratio = fora_s / total if total else 0.0

    return {
        "bands": bands,
        "off_gear_seconds": round(fora_s),
        "off_gear_ratio": round(off_ratio, 3),
        "bands_used": sum(1 for b in bands if b["used"]),
        "bands_total": len(bands),
        "insight": _insight(bands, off_ratio),
    }


def _insight(bands: list[dict], off_ratio: float) -> str:
    """O texto da tela. So fala do que tem tamanho para significar alguma coisa."""
    nao_usadas = [b for b in bands if not b["used"]]
    total = len(bands)

    if not nao_usadas:
        texto = f"Voce passou pelas {total} faixas de marcha da bike neste pedal."
    else:
        nomes = ", ".join(b["label"] for b in nao_usadas[:3])
        resto = f" e mais {len(nao_usadas) - 3}" if len(nao_usadas) > 3 else ""
        texto = (
            f"{len(nao_usadas)} de {total} faixas ficaram paradas: {nomes}{resto}. "
            f"Num pedal so isso nao quer dizer muito - relacao parada em varios "
            f"pedais seguidos e que vira peso morto no cassete."
        )

    if off_ratio > OFF_GEAR_WARN:
        texto += (
            f" Atencao: {off_ratio * 100:.0f}% do tempo pedalando caiu fora de qualquer "
            f"relacao declarada. Confira os dentes da catraca e a circunferencia do aro - "
            f"com um dos dois errado, o mapa inteiro sai deslocado."
        )
    return texto


# Catalogo para a tela. Cobre o comum, nao o universo - quem tiver transmissao
# fora da lista digita os dentes na mao, que e o caminho de escape do formulario.
PRESETS = {
    "chainrings": [
        {"label": "3x MTB 42-34-24", "value": [42, 34, 24]},
        {"label": "3x MTB 44-32-22", "value": [44, 32, 22]},
        {"label": "2x Speed compacta 50-34", "value": [50, 34]},
        {"label": "2x Speed 52-36", "value": [52, 36]},
        {"label": "2x Speed 53-39", "value": [53, 39]},
        {"label": "2x MTB 36-26", "value": [36, 26]},
        {"label": "1x 32", "value": [32]},
        {"label": "1x 34", "value": [34]},
        {"label": "1x 38", "value": [38]},
        {"label": "1x 40", "value": [40]},
        {"label": "1x 42", "value": [42]},
    ],
    "cassettes": [
        {"label": "7v 14-28", "value": [14, 16, 18, 20, 22, 24, 28]},
        {"label": "7v 14-34", "value": [14, 16, 18, 20, 24, 28, 34]},
        {"label": "8v 11-32", "value": [11, 13, 15, 17, 20, 23, 26, 32]},
        {"label": "9v 11-34", "value": [11, 13, 15, 17, 20, 23, 26, 30, 34]},
        {"label": "10v 11-28", "value": [11, 12, 13, 14, 15, 17, 19, 21, 24, 28]},
        {"label": "10v 11-36", "value": [11, 13, 15, 17, 19, 21, 24, 28, 32, 36]},
        {"label": "11v 11-28", "value": [11, 12, 13, 14, 15, 17, 19, 21, 23, 25, 28]},
        {"label": "11v 11-32", "value": [11, 12, 13, 14, 16, 18, 20, 22, 25, 28, 32]},
        {"label": "11v 11-34", "value": [11, 13, 15, 17, 19, 21, 24, 27, 30, 32, 34]},
        {"label": "11v 11-42", "value": [11, 13, 15, 17, 19, 21, 24, 28, 32, 37, 42]},
        {"label": "12v 10-51", "value": [10, 12, 14, 16, 18, 21, 24, 28, 33, 39, 45, 51]},
    ],
    "wheels": [
        {"label": "700x23c", "value": 2096},
        {"label": "700x25c", "value": 2105},
        {"label": "700x28c", "value": 2136},
        {"label": "700x32c", "value": 2155},
        {"label": "700x38c", "value": 2180},
        {"label": "26x2.1", "value": 2073},
        {"label": "27.5x2.1", "value": 2185},
        {"label": "29x2.1", "value": 2288},
        {"label": "29x2.25", "value": 2300},
    ],
}
