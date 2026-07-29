"""O treinador: le o historico e responde tres perguntas.

Fronteira igual a do drivetrain.py: entra dado, sai leitura. Sem banco, sem HTTP,
sem Session - o router monta os insumos. Por isso da para testar sem nada montado.

A MOEDA AQUI E TEMPO E FREQUENCIA, NAO TSS. O FTP do sistema e um default do
.env que ninguem mediu, e TSS depende dele inteiramente: medido no pedal real de
27/07, o mesmo treino da TSS 28 com FTP 220 e TSS 61 com FTP 150 - vira "leve" ou
"descanso obrigatorio" so mudando um numero que ninguem mediu. Sessenta minutos
sao sessenta minutos.

Para quem treina por peso e constancia, tempo tambem e a metrica fisiologicamente
certa: perda de peso e base aerobica respondem a volume em Z2, nao a intensidade.

O TSB entra em UM lugar so - o sinal de descanso - onde o que importa e o sinal e
a tendencia, nao o valor absoluto. "Voce pedalou quatro dias seguidos e a curva
esta caindo" continua verdade mesmo com o FTP errado.
"""

from __future__ import annotations

from datetime import date, timedelta

# Abaixo disso o treinador nao tem o que ler, e diz isso em vez de inventar.
MIN_RIDES_TO_READ = 3

# Dias de calendario consecutivos com treino que ja pedem uma folga.
CONSECUTIVE_DAYS_REST = 4

# TSB abaixo disso E caindo = carga subiu rapido demais.
TSB_LOW = -20.0
TSB_TREND_DAYS = 3

# A partir daqui o treinador convida de volta - sem cobrar (R5).
ABSENCE_DAYS = 5

SEVERITY = "info"  # R4: nunca alarme. Vermelho neste app e FC.


def _consecutive_days(rides: list[dict], hoje: date) -> int:
    """Dias de calendario seguidos com treino, terminando ontem ou hoje.

    Sequencia que terminou semana passada nao produz fadiga hoje, entao so conta
    se encostar no presente.
    """
    dias = {r["date"] for r in rides}
    if hoje not in dias and (hoje - timedelta(days=1)) not in dias:
        return 0
    inicio = hoje if hoje in dias else hoje - timedelta(days=1)
    n = 0
    while inicio - timedelta(days=n) in dias:
        n += 1
    return n


def _tsb_now_and_before(pmc: list[dict], hoje: date) -> tuple[float | None, float | None]:
    """TSB de hoje e o de TSB_TREND_DAYS atras, para saber a direcao."""
    por_data = {p["date"]: p["tsb"] for p in pmc}
    agora = por_data.get(hoje.isoformat())
    antes = por_data.get((hoje - timedelta(days=TSB_TREND_DAYS)).isoformat())
    return agora, antes


def readiness(rides: list[dict], pmc: list[dict], hoje: date) -> dict:
    """Devo pedalar hoje? Poucas regras, avaliadas em ordem.

    So fala quando tem o que dizer - mesmo principio do 3.4 da SPEC principal.
    Um sistema que sempre acha um motivo mente com confianca.
    """
    if len(rides) < MIN_RIDES_TO_READ:
        faltam = MIN_RIDES_TO_READ - len(rides)
        return {
            "state": "sem_historico",
            "severity": SEVERITY,
            "rides_needed": faltam,
            "headline": "Ainda não tenho histórico pra ler",
            "detail": (
                f"Faltam {faltam} pedal(is) pra eu conseguir dizer alguma coisa útil sobre "
                f"hoje. Até lá, o melhor conselho é simples: pedale no ritmo que der pra "
                f"conversar, e volte aqui quando tiver mais alguns treinos no banco."
            ),
        }

    seguidos = _consecutive_days(rides, hoje)
    if seguidos >= CONSECUTIVE_DAYS_REST:
        return {
            "state": "folga",
            "severity": SEVERITY,
            "rides_needed": 0,
            "headline": "Vale uma folga hoje",
            "detail": (
                f"São {seguidos} dias seguidos na sela. O ganho de um treino acontece no "
                f"descanso depois dele, não durante - um dia parado agora rende mais que "
                f"um dia pedalado."
            ),
        }

    agora, antes = _tsb_now_and_before(pmc, hoje)
    if agora is not None and antes is not None and agora < TSB_LOW and agora < antes:
        return {
            "state": "leve",
            "severity": SEVERITY,
            "rides_needed": 0,
            "headline": "Hoje, leve",
            "detail": (
                "Sua carga subiu rápido nos últimos dias e ainda está subindo. Não é caso "
                "de parar, é caso de pedalar curto e tranquilo."
            ),
        }

    ultimo = max(r["date"] for r in rides)
    parado = (hoje - ultimo).days
    if parado >= ABSENCE_DAYS:
        return {
            "state": "convite",
            "severity": SEVERITY,
            "rides_needed": 0,
            "headline": "Bom dia pra voltar",
            "detail": (
                f"Seu último pedal foi há {parado} dias. Não precisa ser longo nem rápido - "
                f"sair e voltar já recoloca o hábito no lugar."
            ),
        }

    return {
        "state": "livre",
        "severity": SEVERITY,
        "rides_needed": 0,
        "headline": "Dia livre",
        "detail": "Nada no seu histórico recente pede cautela hoje.",
    }


# R2: a meta sugerida sobe no maximo isso sobre a media de 4 semanas.
RAMP_CAP = 0.10
RAMP_WEEKS = 4
# Abaixo deste ganho nao vale sugerir nada - so ruido.
MIN_SUGGESTION_GAIN = 0.05

# Teto e piso da sessao prescrita.
MAX_SESSION_MULTIPLIER = 1.5
MIN_SESSION_MIN = 20

ZONE = "Z2"
PACE = "ritmo de conversa"


def prescription(readiness: dict, goal: dict, week: dict, recent: dict) -> dict:
    """O que faco hoje? Duracao e zona - nunca intensidade (R1).

    A conta e o que falta da meta dividido pelos pedais que sobram na semana,
    com teto de 1,5x o pedal mais longo recente. O teto existe para nao sugerir
    tres horas a quem vem fazendo quarenta e cinco minutos: meta agressiva e o
    caminho mais curto para o abandono.
    """
    if readiness["state"] == "folga":
        return {
            "kind": "folga",
            "minutes": None,
            "zone": None,
            "headline": "Hoje é dia de descanso",
            "detail": readiness["detail"],
        }

    faltam_min = max(0.0, goal["minutes_per_week"] - week["minutes_done"])
    faltam_pedais = goal["rides_per_week"] - week["rides_done"]

    if faltam_min <= 0 and faltam_pedais <= 0:
        minutos = _clamp(recent["avg_ride_min"], recent)
        return {
            "kind": "bonus",
            "minutes": minutos,
            "zone": ZONE,
            "headline": f"Meta da semana batida - {minutos} min de bônus, se quiser",
            "detail": (
                f"Você já fechou os {goal['rides_per_week']} pedais e os "
                f"{goal['minutes_per_week']} minutos. O que vier agora é lucro: "
                f"vá no {PACE}, ou fique em casa com a consciência tranquila."
            ),
        }

    # max(1, ...) cobre ter batido a contagem de pedais mas nao a de minutos -
    # sem ele a conta divide por zero.
    bruto = faltam_min / max(1, faltam_pedais)
    minutos = _clamp(bruto, recent)

    if readiness["state"] == "leve":
        minutos = MIN_SESSION_MIN
        detalhe = f"Curto e tranquilo hoje: {minutos} min no {PACE}. {readiness['detail']}"
    else:
        detalhe = (
            f"Faltam {faltam_min:.0f} min pra fechar sua semana. Este pedal no {PACE} - "
            f"aquele em que você consegue falar frases inteiras sem perder o fôlego - "
            f"resolve boa parte."
        )

    return {
        "kind": "pedal",
        "minutes": minutos,
        "zone": ZONE,
        "headline": f"{minutos} min no {PACE}",
        "detail": detalhe,
    }


def _clamp(minutos: float, recent: dict) -> int:
    """Teto de 1,5x o pedal mais longo recente, piso de 20 min."""
    teto = max(MIN_SESSION_MIN, recent["longest_ride_min"] * MAX_SESSION_MULTIPLIER)
    return int(round(max(MIN_SESSION_MIN, min(minutos, teto))))


def suggest_goal(goal: dict, weeks: list[dict]) -> dict | None:
    """Sugere uma meta maior - ou nao sugere nada, que e o caso comum.

    Devolve None em vez de forcar: quem altera a meta e o usuario, e ignorar a
    sugestao nao tem consequencia. R2 limita o tamanho do passo, R3 desliga a
    sugestao depois de uma semana abaixo da meta.
    """
    if len(weeks) < RAMP_WEEKS:
        return None
    ultimas = weeks[-RAMP_WEEKS:]

    # R3: nao bateu a meta na semana passada? Entao a meta ja esta no limite.
    if not ultimas[-1]["met_goal"]:
        return None

    media = sum(w["minutes"] for w in ultimas) / RAMP_WEEKS

    atual = goal["minutes_per_week"]
    # So vale sugerir se a media REAL ja passa a meta atual por uma margem
    # clara. Media apenas empatada com a meta (bateu raspando) nao e sinal de
    # sobra de capacidade - e so a meta sendo cumprida, o que R3 ja cobre.
    if media < atual * (1 + MIN_SUGGESTION_GAIN):
        return None

    # R2: teto de +10% sobre a media REAL, nao sobre a meta declarada - senao a
    # meta poderia disparar enquanto o volume de verdade fica para tras.
    sugerido = media * (1 + RAMP_CAP)

    return {
        "minutes_per_week": int(round(sugerido)),
        "rides_per_week": goal["rides_per_week"],
        "reason": (
            f"Você vem fechando a meta e ficou numa média de {media:.0f} min por semana. "
            f"Se quiser, dá pra subir pra {sugerido:.0f} min sem apertar - mas só se "
            f"parecer natural. A meta é sua."
        ),
    }


PROGRESS_WEEKS = 8


def _week_start(d: date) -> date:
    """Segunda-feira da semana de d - mesmo criterio ISO do /api/stats/trend."""
    return d - timedelta(days=d.weekday())


def progress(rides: list[dict], weights: list[dict], goal: dict, hoje: date) -> dict:
    """Estou evoluindo?

    A ordem das linhas nao e decorativa: constancia primeiro, potencia por
    ultimo. Ela reflete o objetivo do ciclista - peso e habito - e nao a
    sofisticacao da metrica.
    """
    inicio = _week_start(hoje) - timedelta(weeks=PROGRESS_WEEKS - 1)
    baldes: dict[date, dict] = {}
    for r in rides:
        semana = _week_start(r["date"])
        if semana < inicio:
            continue
        b = baldes.setdefault(semana, {"rides": 0, "minutes": 0.0})
        b["rides"] += 1
        b["minutes"] += r["minutes"]

    semanas = [
        {
            "week": s.isoformat(),
            "rides": baldes[s]["rides"],
            "minutes": round(baldes[s]["minutes"]),
            "met_goal": (
                baldes[s]["rides"] >= goal["rides_per_week"]
                and baldes[s]["minutes"] >= goal["minutes_per_week"]
            ),
        }
        for s in sorted(baldes)
    ]

    peso = None
    if weights:
        ordenado = sorted(weights, key=lambda w: w["date"])
        primeiro, ultimo = ordenado[0], ordenado[-1]
        peso = {
            "current_kg": ultimo["weight_kg"],
            "first_kg": primeiro["weight_kg"],
            "change_kg": round(ultimo["weight_kg"] - primeiro["weight_kg"], 1),
            "target_kg": goal.get("target_weight_kg"),
            "series": [
                {"date": w["date"].isoformat(), "weight_kg": w["weight_kg"]} for w in ordenado
            ],
        }

    return {
        "consistency": {
            "weeks": semanas,
            "goal_rides": goal["rides_per_week"],
            "goal_minutes": goal["minutes_per_week"],
        },
        "weight": peso,
    }
