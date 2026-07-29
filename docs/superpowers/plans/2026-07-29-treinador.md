# Aba Treinador — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Uma aba que lê o histórico e responde três perguntas — pedalo hoje, o que faço, estou evoluindo — com a moeda em tempo e frequência, nunca em TSS.

**Architecture:** Um módulo puro `services/coach.py` recebe listas de dicionários simples e devolve três leituras; não conhece banco, HTTP nem ORM. Dois routers finos montam os insumos e compõem. Duas tabelas novas (peso e meta) que o `create_all()` cria sozinho. O registro de peso também corrige o modelo de potência, hoje congelado num valor fixo do `.env`.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0, pytest. Angular 19 standalone, Chart.js 4.

**Spec:** `docs/superpowers/specs/2026-07-29-treinador-design.md`

> ⚠️ **DECISÃO DO USUÁRIO: este projeto não usa git.**
> **Pule TODO passo de commit** (`git add` / `git commit`). Não rode `git init`. Todo o resto
> — código, testes e verificações — vale normalmente.

> ℹ️ **Ambiente.** Python: `d:/AI Solution/Bike_Graph/backend/.venv/Scripts/python.exe`.
> Testes: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q` (30 passando hoje).
> Servidores em `localhost:8000` e `localhost:4200` podem estar rodando **sem `--reload` no
> backend** — mudança em Python só vale depois de reiniciar, e quem reinicia é o controlador,
> não você. Use `fastapi.testclient.TestClient` para checar HTTP.

---

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `backend/app/services/coach.py` | **Criar.** As três leituras e as cinco regras. Puro: sem banco, sem HTTP. |
| `backend/tests/test_coach.py` | **Criar.** As cinco regras viram cinco testes. |
| `backend/app/routers/coach.py` | **Criar.** `/api/coach`, `/api/coach/goal`. |
| `backend/app/routers/weight.py` | **Criar.** `/api/weight`. Separado porque peso é dado do atleta, não do treinador. |
| `backend/app/models.py` | **Modificar.** `WeightEntry`, `CoachGoal`. |
| `backend/app/main.py` | **Modificar.** Registrar os dois routers. |
| `backend/app/services/ingest.py` | **Modificar.** Usar o peso da data do treino. |
| `frontend/src/app/pages/coach.component.ts` | **Criar.** A aba inteira. |
| `frontend/src/app/core/models.ts` | **Modificar.** Tipos. |
| `frontend/src/app/core/api.service.ts` | **Modificar.** Chamadas. |
| `frontend/src/app/app.routes.ts` | **Modificar.** Rota `/treinador`. |
| `frontend/src/app/app.component.ts` | **Modificar.** Item de menu. |

---

## Task 1: Tabelas de peso e meta

**Files:** Modify `backend/app/models.py`

- [ ] **Step 1: Acrescentar as duas classes ao final do arquivo**

```python
class WeightEntry(Base):
    """Peso do ciclista ao longo do tempo.

    Existe por dois motivos. O primeiro e obvio: metade do objetivo do usuario e
    perder peso, e sem serie nao ha tendencia. O segundo e silencioso e talvez
    mais importante: o modelo de potencia usa a massa total na conta da fisica, e
    hoje ele le um valor fixo do .env. Quem emagrece 8 kg segue tendo a potencia
    calculada com o corpo antigo, e a comparacao entre meses fica contaminada.
    """

    __tablename__ = "weight_entries"
    __table_args__ = (UniqueConstraint("measured_on", name="uq_weight_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Um lancamento por dia. Relancar o mesmo dia sobrescreve, senao tres
    # pesagens da mesma manha brigam pela linha de tendencia.
    measured_on: Mapped[date] = mapped_column(Date, index=True)
    weight_kg: Mapped[float] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class CoachGoal(Base):
    """A meta de constancia, declarada pelo usuario. Linha unica (id=1).

    O treinador pode SUGERIR uma meta maior, mas quem altera e o usuario - e a
    sugestao e limitada a +10% da media de 4 semanas e desligada depois de uma
    semana abaixo da meta. Ver as regras R2 e R3 do spec.
    """

    __tablename__ = "coach_goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    rides_per_week: Mapped[int] = mapped_column(Integer, default=3)
    minutes_per_week: Mapped[int] = mapped_column(Integer, default=180)
    target_weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 2: Acertar os imports no topo do arquivo**

O arquivo já importa `datetime` de `datetime` e vários tipos de `sqlalchemy`. Faltam `date` e `Date`. Trocar as duas primeiras linhas de import por:

```python
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
```

- [ ] **Step 3: Verificar que as tabelas nascem**

São tabelas NOVAS, então `Base.metadata.create_all()` cria sozinho — sem `ALTER TABLE`.

```bash
cd "d:/AI Solution/Bike_Graph/backend"
./.venv/Scripts/python.exe -c "
from app.database import Base, engine
import app.models  # registra as classes
Base.metadata.create_all(bind=engine)
import sqlite3
con = sqlite3.connect('igpsport.db')
print([r[0] for r in con.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")])
print('bikes preservadas:', list(con.execute('SELECT id, name FROM bikes')))
print('treinos preservados:', list(con.execute('SELECT count(*) FROM activities')))
"
```

Esperado: a lista inclui `weight_entries` e `coach_goals`, e a bike e o treino continuam lá.

---

## Task 2: O módulo `coach.py` — prontidão

**Files:** Create `backend/app/services/coach.py`, Create `backend/tests/test_coach.py`

- [ ] **Step 1: Escrever os testes que falham**

Criar `backend/tests/test_coach.py`:

```python
"""Testes do treinador.

As cinco regras do "sem forcar" (R1 a R5 do spec) sao invariantes, nao tom de
voz - cada uma tem um teste que quebra o build se alguem as violar.
"""

from datetime import date, timedelta

import pytest

from app.services import coach

HOJE = date(2026, 8, 31)  # uma segunda-feira


def _rides(dias_atras: list[int], minutos: float = 60.0) -> list[dict]:
    """Treinos a N dias de hoje. dias_atras=[0] e um treino hoje."""
    return [
        {"date": HOJE - timedelta(days=d), "minutes": minutos, "load": 30.0}
        for d in dias_atras
    ]


def _pmc(tsb_por_dia: dict[int, float]) -> list[dict]:
    """PMC no formato do /api/stats/pmc: {dias_atras: tsb}."""
    return [
        {"date": (HOJE - timedelta(days=d)).isoformat(), "tsb": v}
        for d, v in sorted(tsb_por_dia.items(), reverse=True)
    ]


def test_sem_historico_admite_que_nao_sabe():
    r = coach.readiness(_rides([2]), _pmc({0: 0.0}), HOJE)
    assert r["state"] == "sem_historico"
    assert "hist" in r["headline"].lower()
    assert r["rides_needed"] == coach.MIN_RIDES_TO_READ - 1


def test_quatro_dias_seguidos_pede_folga():
    r = coach.readiness(_rides([0, 1, 2, 3]), _pmc({0: 0.0}), HOJE)
    assert r["state"] == "folga"


def test_tres_dias_seguidos_ainda_nao_pede_folga():
    r = coach.readiness(_rides([0, 1, 2]), _pmc({0: 0.0}), HOJE)
    assert r["state"] != "folga"


def test_sequencia_antiga_nao_conta():
    # 4 dias seguidos, mas terminaram ha uma semana: nao ha fadiga a respeitar
    r = coach.readiness(_rides([7, 8, 9, 10]), _pmc({0: 0.0}), HOJE)
    assert r["state"] != "folga"


def test_tsb_baixo_e_caindo_pede_leve():
    r = coach.readiness(_rides([1, 4, 8]), _pmc({0: -25.0, 3: -10.0}), HOJE)
    assert r["state"] == "leve"


def test_tsb_baixo_mas_subindo_nao_pede_leve():
    # Ja esta se recuperando: -25 hoje contra -40 tres dias atras
    r = coach.readiness(_rides([1, 4, 8]), _pmc({0: -25.0, 3: -40.0}), HOJE)
    assert r["state"] == "livre"


def test_ausencia_longa_vira_convite():
    r = coach.readiness(_rides([9, 14, 20]), _pmc({0: 5.0, 3: 3.0}), HOJE)
    assert r["state"] == "convite"


def test_dia_normal_e_livre():
    r = coach.readiness(_rides([1, 4, 8]), _pmc({0: 0.0, 3: 0.0}), HOJE)
    assert r["state"] == "livre"


# --- R4: descanso nunca e alarme -----------------------------------------

def test_descanso_nunca_e_alarme():
    """R4. Vermelho neste app e FC, e continua sendo so isso."""
    cenarios = [
        coach.readiness(_rides([0, 1, 2, 3]), _pmc({0: 0.0}), HOJE),
        coach.readiness(_rides([1, 4, 8]), _pmc({0: -25.0, 3: -10.0}), HOJE),
        coach.readiness(_rides([0, 1, 2, 3, 4, 5, 6]), _pmc({0: -60.0, 3: -20.0}), HOJE),
    ]
    for r in cenarios:
        assert r["severity"] == "info", r["state"]


# --- R5: ausencia gera convite, nao cobranca ------------------------------

COBRANCA = [
    "deveria", "devia", "falhou", "falhar", "perdeu", "fracasso", "preguica",
    "desculpa", "vergonha", "abandonou", "desistiu", "atrasado",
]


def test_ausencia_nao_gera_cobranca():
    """R5. App de habito que envergonha e app desinstalado.

    Tres treinos para passar do MIN_RIDES_TO_READ - com dois, isto caia em
    "sem_historico" e testava a mensagem errada, passando por acidente. O assert
    do state existe para fixar o galho e impedir que volte a derivar.
    """
    for dias in (6, 10, 21, 60):
        r = coach.readiness(
            _rides([dias, dias + 5, dias + 10]), _pmc({0: 5.0, 3: 5.0}), HOJE
        )
        assert r["state"] == "convite", f"{dias} dias deveria virar convite, veio {r['state']}"
        texto = (r["headline"] + " " + r["detail"]).lower()
        for palavra in COBRANCA:
            assert palavra not in texto, f"{dias} dias: '{palavra}' em {texto!r}"
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
cd "d:/AI Solution/Bike_Graph/backend"
./.venv/Scripts/python.exe -m pytest tests/test_coach.py -v
```

Esperado: FAIL — `ModuleNotFoundError: No module named 'app.services.coach'`

- [ ] **Step 3: Implementar**

Criar `backend/app/services/coach.py`:

```python
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
            "headline": "Ainda nao tenho historico pra ler",
            "detail": (
                f"Faltam {faltam} pedal(is) pra eu conseguir dizer alguma coisa util sobre "
                f"hoje. Ate la, o melhor conselho e simples: pedale no ritmo que der pra "
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
                f"Sao {seguidos} dias seguidos na sela. O ganho de um treino acontece no "
                f"descanso depois dele, nao durante - um dia parado agora rende mais que "
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
                "Sua carga subiu rapido nos ultimos dias e ainda esta subindo. Nao e caso "
                "de parar, e caso de pedalar curto e tranquilo."
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
                f"Seu ultimo pedal foi ha {parado} dias. Nao precisa ser longo nem rapido - "
                f"sair e voltar ja recoloca o habito no lugar."
            ),
        }

    return {
        "state": "livre",
        "severity": SEVERITY,
        "rides_needed": 0,
        "headline": "Dia livre",
        "detail": "Nada no seu historico recente pede cautela hoje.",
    }
```

- [ ] **Step 4: Rodar e confirmar que passam**

```bash
cd "d:/AI Solution/Bike_Graph/backend"
./.venv/Scripts/python.exe -m pytest tests/test_coach.py -v
```

Esperado: 11 passed. Rodar também `pytest tests/ -q` → 41 passed (30 antigos + 11).

---

## Task 3: Prescrição e as regras R1, R2, R3

**Files:** Modify `backend/app/services/coach.py`, Modify `backend/tests/test_coach.py`

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar a `backend/tests/test_coach.py`:

```python
META = {"rides_per_week": 3, "minutes_per_week": 180}
RECENTE = {"longest_ride_min": 60.0, "avg_ride_min": 50.0, "weeks_avg_minutes": 150.0}


def _livre():
    return coach.readiness(_rides([1, 4, 8]), _pmc({0: 0.0, 3: 0.0}), HOJE)


def test_folga_manda_na_prescricao():
    r = coach.readiness(_rides([0, 1, 2, 3]), _pmc({0: 0.0}), HOJE)
    p = coach.prescription(r, META, {"rides_done": 2, "minutes_done": 100.0}, RECENTE)
    assert p["kind"] == "folga"
    assert p["minutes"] is None


def test_divide_o_que_falta_pelos_pedais_restantes():
    # meta 180, feitos 60, faltam 2 pedais -> 60 min cada
    p = coach.prescription(_livre(), META, {"rides_done": 1, "minutes_done": 60.0}, RECENTE)
    assert p["kind"] == "pedal"
    assert p["minutes"] == 60


def test_nao_divide_por_zero_quando_a_contagem_ja_foi_batida():
    # 3 pedais feitos mas so 100 dos 180 minutos: faltam 80, e nao ha pedal "restante"
    p = coach.prescription(_livre(), META, {"rides_done": 3, "minutes_done": 100.0}, RECENTE)
    assert p["kind"] == "pedal"
    assert p["minutes"] == 80


def test_meta_batida_vira_bonus_sem_cobranca():
    p = coach.prescription(_livre(), META, {"rides_done": 3, "minutes_done": 200.0}, RECENTE)
    assert p["kind"] == "bonus"
    assert p["minutes"] == 50  # a duracao tipica recente


def test_teto_de_uma_vez_e_meia_o_pedal_mais_longo():
    magra = {"rides_per_week": 1, "minutes_per_week": 600}
    p = coach.prescription(_livre(), magra, {"rides_done": 0, "minutes_done": 0.0}, RECENTE)
    assert p["minutes"] == 90  # 1.5 * 60, e nao 600


def test_piso_de_vinte_minutos():
    p = coach.prescription(_livre(), META, {"rides_done": 2, "minutes_done": 175.0}, RECENTE)
    assert p["minutes"] >= coach.MIN_SESSION_MIN


# --- R1: nunca acima de Z2 ------------------------------------------------

INTENSIDADE = ["limiar", "tiro", "intervalado", "vo2", "z3", "z4", "z5", "anaerobic", "sprint"]


def test_nunca_prescreve_acima_de_z2():
    """R1. O vocabulario e duracao + ritmo de conversa. Nao existe tiro."""
    prontidoes = [
        _livre(),
        coach.readiness(_rides([0, 1, 2, 3]), _pmc({0: 0.0}), HOJE),
        coach.readiness(_rides([1, 4, 8]), _pmc({0: -25.0, 3: -10.0}), HOJE),
        coach.readiness(_rides([2]), _pmc({0: 0.0}), HOJE),
        coach.readiness(_rides([9, 14, 20]), _pmc({0: 5.0, 3: 5.0}), HOJE),
    ]
    semanas = [
        {"rides_done": 0, "minutes_done": 0.0},
        {"rides_done": 2, "minutes_done": 100.0},
        {"rides_done": 5, "minutes_done": 400.0},
    ]
    for pr in prontidoes:
        for sem in semanas:
            p = coach.prescription(pr, META, sem, RECENTE)
            assert p["zone"] in ("Z2", None), p
            texto = (p["headline"] + " " + p["detail"]).lower()
            for palavra in INTENSIDADE:
                assert palavra not in texto, f"{palavra!r} em {texto!r}"


# --- R2 e R3: a sugestao de meta ------------------------------------------

def _semanas(minutos: list[float], bateu: list[bool]) -> list[dict]:
    return [{"minutes": m, "rides": 3, "met_goal": b} for m, b in zip(minutos, bateu)]


def test_nunca_sobe_mais_que_10_por_cento():
    """R2. Media de 200 min -> no maximo 220."""
    s = coach.suggest_goal(META, _semanas([200, 200, 200, 200], [True] * 4))
    assert s is not None
    assert s["minutes_per_week"] <= 220


def test_nunca_sobe_depois_de_semana_abaixo():
    """R3. Nao bateu = meta ja esta alta, ou a vida atravessou."""
    s = coach.suggest_goal(META, _semanas([200, 200, 200, 90], [True, True, True, False]))
    assert s is None


def test_sem_quatro_semanas_nao_sugere_nada():
    s = coach.suggest_goal(META, _semanas([200, 200], [True, True]))
    assert s is None


def test_nao_sugere_quando_ja_esta_no_lugar():
    # media 180 contra meta 180: subir 10% daria 198, ganho pequeno demais
    s = coach.suggest_goal(META, _semanas([180, 180, 180, 180], [True] * 4))
    assert s is None
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_coach.py -v
```

Esperado: FAIL — `AttributeError: module 'app.services.coach' has no attribute 'prescription'`

- [ ] **Step 3: Implementar** — acrescentar ao final de `coach.py`

```python
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
            "headline": "Hoje e dia de descanso",
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
            "headline": f"Meta da semana batida — {minutos} min de bonus, se quiser",
            "detail": (
                f"Voce ja fechou os {goal['rides_per_week']} pedais e os "
                f"{goal['minutes_per_week']} minutos. O que vier agora e lucro: "
                f"vá no {PACE}, ou fique em casa com a consciencia tranquila."
            ),
        }

    # max(1, ...) cobre ter batido a contagem de pedais mas nao a de minutos -
    # sem ele a conta divide por zero.
    bruto = faltam_min / max(1, faltam_pedais)
    minutos = _clamp(bruto, recent)

    if readiness["state"] == "leve":
        minutos = MIN_SESSION_MIN
        detalhe = (
            f"Curto e tranquilo hoje: {minutos} min no {PACE}. "
            f"{readiness['detail']}"
        )
    else:
        detalhe = (
            f"Faltam {faltam_min:.0f} min pra fechar sua semana. Este pedal no {PACE} — "
            f"aquele em que voce consegue falar frases inteiras sem perder o folego — "
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

    # So sugere subir se existe FOLGA de verdade: a media real precisa estar
    # acima da meta atual por uma margem. Comparar a sugestao hipotetica com a
    # meta seria outra pergunta, e a errada - com media 180 contra meta 180 ela
    # mandaria subir para 198, ou seja, propor um aumento a quem esta apenas
    # empatando com o proprio alvo.
    if media < atual * (1 + MIN_SUGGESTION_GAIN):
        return None

    # R2: teto de +10% sobre a media REAL, nao sobre a meta declarada - senao a
    # meta poderia disparar enquanto o volume de verdade fica para tras.
    sugerido = media * (1 + RAMP_CAP)

    return {
        "minutes_per_week": int(round(sugerido)),
        "rides_per_week": goal["rides_per_week"],
        "reason": (
            f"Voce vem fechando a meta e ficou numa media de {media:.0f} min por semana. "
            f"Se quiser, da pra subir pra {sugerido:.0f} min sem apertar — mas so se "
            f"parecer natural. A meta e sua."
        ),
    }
```

- [ ] **Step 4: Rodar e confirmar que passam**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_coach.py -v
```

Esperado: 23 passed. `pytest tests/ -q` → 53 passed.

---

## Task 4: Progresso

**Files:** Modify `backend/app/services/coach.py`, Modify `backend/tests/test_coach.py`

- [ ] **Step 1: Escrever os testes**

Acrescentar a `backend/tests/test_coach.py`:

```python
def test_progresso_conta_semanas_de_constancia():
    rides = _rides([1, 3, 5, 8, 10, 12], minutos=60.0)
    p = coach.progress(rides, [], META, HOJE)
    assert p["consistency"]["weeks"][-1]["rides"] >= 1
    assert p["consistency"]["goal_rides"] == 3


def test_progresso_sem_peso_nao_mostra_linha_de_peso():
    p = coach.progress(_rides([1, 3]), [], META, HOJE)
    assert p["weight"] is None


def test_progresso_com_peso_calcula_variacao():
    pesos = [
        {"date": HOJE - timedelta(days=30), "weight_kg": 82.0},
        {"date": HOJE - timedelta(days=1), "weight_kg": 79.5},
    ]
    p = coach.progress(_rides([1, 3]), pesos, META, HOJE)
    assert p["weight"]["current_kg"] == 79.5
    assert p["weight"]["change_kg"] == pytest.approx(-2.5)


def test_progresso_sem_treino_nenhum_nao_quebra():
    p = coach.progress([], [], META, HOJE)
    assert p["consistency"]["weeks"] == []
    assert p["weight"] is None
```

- [ ] **Step 2: Rodar e confirmar que falha**

Esperado: `AttributeError: ... has no attribute 'progress'`

- [ ] **Step 3: Implementar** — acrescentar ao final de `coach.py`

```python
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
```

- [ ] **Step 4: Rodar** → 27 passed em `test_coach.py`, 57 em `tests/`.

---

## Task 5: Peso corrige o modelo de potência

**Files:** Modify `backend/app/services/ingest.py`

- [ ] **Step 1: Acrescentar o helper**

Em `backend/app/services/ingest.py`, acrescentar o import e a função antes de `import_file`:

```python
from ..models import Activity, ActivityStream, SyncLog, WeightEntry


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
```

- [ ] **Step 2: Usar o helper**

Em `import_file()`, trocar a linha:

```python
            total_mass_kg=settings.rider_weight_kg + bike_weight,
```

por:

```python
            total_mass_kg=_rider_weight_on(db, parsed.started_at) + bike_weight,
```

- [ ] **Step 3: Verificar que nada mudou sem peso lançado**

```bash
cd "d:/AI Solution/Bike_Graph/backend"
./.venv/Scripts/python.exe -c "
from app.database import SessionLocal
from app.services.ingest import _rider_weight_on
from datetime import datetime
with SessionLocal() as db:
    print('sem peso lancado ->', _rider_weight_on(db, datetime(2026,7,27)), '(esperado 75.0, o do .env)')
"
```

- [ ] **Step 4: Documentar o efeito colateral no README**

Em `README.md`, logo depois do bloco sobre colunas novas no banco:

```markdown
**Peso e potência estimada:** se você lançar pesos antigos na aba Treinador e rodar
`POST /api/sync?force=true`, os números de potência dos treinos antigos mudam — passam a ser
calculados com o peso que você tinha naquela data, não com o valor fixo do `.env`. É a
correção certa, mas não se assuste com os valores diferentes.
```

---

## Task 6: Endpoints de peso

**Files:** Create `backend/app/routers/weight.py`, Modify `backend/app/main.py`

- [ ] **Step 1: Criar o router**

```python
"""Peso do ciclista. Fora do namespace do treinador de proposito: e dado do
atleta, alimenta o modelo de potencia, e sobrevive a aba que o exibe."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import WeightEntry

router = APIRouter(prefix="/api/weight", tags=["peso"])


class WeightInput(BaseModel):
    measured_on: date
    weight_kg: float
    note: str | None = None

    @field_validator("weight_kg")
    @classmethod
    def _peso_plausivel(cls, v):
        if not 30 <= v <= 250:
            raise ValueError("Peso fora da faixa plausivel (30 a 250 kg)")
        return round(v, 1)

    @field_validator("measured_on")
    @classmethod
    def _nao_pode_ser_futuro(cls, v):
        if v > date.today():
            raise ValueError("Nao da para pesar no futuro")
        return v


@router.get("")
def list_weight(db: Session = Depends(get_db)):
    entries = db.scalars(select(WeightEntry).order_by(WeightEntry.measured_on))
    return [
        {"measured_on": e.measured_on.isoformat(), "weight_kg": e.weight_kg, "note": e.note}
        for e in entries
    ]


@router.post("", status_code=201)
def log_weight(payload: WeightInput, db: Session = Depends(get_db)):
    """Upsert por data: relancar o mesmo dia corrige, nao duplica."""
    entry = db.scalar(select(WeightEntry).where(WeightEntry.measured_on == payload.measured_on))
    if entry is None:
        entry = WeightEntry(measured_on=payload.measured_on)
        db.add(entry)
    entry.weight_kg = payload.weight_kg
    entry.note = payload.note
    db.commit()
    return {"measured_on": entry.measured_on.isoformat(), "weight_kg": entry.weight_kg}


@router.delete("/{measured_on}", status_code=204)
def delete_weight(measured_on: date, db: Session = Depends(get_db)):
    entry = db.scalar(select(WeightEntry).where(WeightEntry.measured_on == measured_on))
    if entry is None:
        raise HTTPException(404, "Sem registro de peso nessa data")
    db.delete(entry)
    db.commit()
```

- [ ] **Step 2: Registrar em `main.py`**

Trocar a linha de import dos routers por:
```python
from .routers import activities, analysis, bikes, coach, stats, sync, weight
```
E acrescentar depois de `app.include_router(sync.router)`:
```python
app.include_router(coach.router)
app.include_router(weight.router)
```

O `coach` ainda não existe — a Task 7 o cria. Fazer os dois na ordem e só então testar.

---

## Task 7: Endpoints do treinador

**Files:** Create `backend/app/routers/coach.py`

- [ ] **Step 1: Criar o router**

```python
"""A aba Treinador. O router monta os insumos e compoe; a leitura mora no
services/coach.py, que nao conhece banco nem HTTP."""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Activity, CoachGoal, WeightEntry
from ..services import coach as coach_service
from ..services import metrics

router = APIRouter(prefix="/api/coach", tags=["treinador"])

RECENT_WEEKS = 4


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
        "ftp_is_default": get_settings().ftp_watts == 220,
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
```

- [ ] **Step 2: Verificar por TestClient**

Escrever em `C:/Users/User/AppData/Local/Temp/claude/d--AI-Solution-Bike-Graph/73af56df-2a4e-44d1-8c11-710868d91342/scratchpad/check_coach.py` e rodar de dentro de `backend/`:

```python
import sys
from datetime import date, timedelta

sys.path.insert(0, "d:/AI Solution/Bike_Graph/backend")
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)

print("=== GET /api/coach ===")
r = c.get("/api/coach")
print("status:", r.status_code)
d = r.json()
print("  readiness :", d["readiness"]["state"], "|", d["readiness"]["headline"])
print("  faltam    :", d["readiness"]["rides_needed"], "pedal(is)")
print("  prescricao:", d["prescription"]["kind"], d["prescription"]["minutes"], d["prescription"]["zone"])
print("  meta      :", d["goal"])
print("  sugestao  :", d["goal_suggestion"])
print("  ctl       :", d["progress"]["fitness"]["ctl"])
print("  ftp padrao:", d["ftp_is_default"])
assert d["readiness"]["state"] == "sem_historico", "com 1 treino tem que admitir que nao sabe"
assert d["readiness"]["rides_needed"] == 2

print("\n=== PUT /api/coach/goal ===")
r = c.put("/api/coach/goal", json={"rides_per_week": 4, "minutes_per_week": 240})
print("status:", r.status_code, r.json())
assert r.status_code == 200 and r.json()["rides_per_week"] == 4

print("\n=== meta invalida deve dar 422 ===")
r = c.put("/api/coach/goal", json={"rides_per_week": 0, "minutes_per_week": 240})
print("status:", r.status_code)
assert r.status_code == 422

print("\n=== POST /api/weight ===")
hoje = date.today().isoformat()
r = c.post("/api/weight", json={"measured_on": hoje, "weight_kg": 82.4})
print("status:", r.status_code, r.json())
r = c.post("/api/weight", json={"measured_on": hoje, "weight_kg": 82.1})  # upsert
print("upsert:", r.status_code, r.json())
assert c.get("/api/weight").json()[-1]["weight_kg"] == 82.1, "relancar o mesmo dia tem que corrigir"

print("\n=== peso no futuro deve dar 422 ===")
amanha = (date.today() + timedelta(days=1)).isoformat()
r = c.post("/api/weight", json={"measured_on": amanha, "weight_kg": 80.0})
print("status:", r.status_code)
assert r.status_code == 422

print("\n=== o peso passou a alimentar o progresso? ===")
d = c.get("/api/coach").json()
print("  peso agora:", d["progress"]["weight"])
assert d["progress"]["weight"] is not None

print("\n=== restaurando a meta padrao ===")
c.put("/api/coach/goal", json={"rides_per_week": 3, "minutes_per_week": 180})
print("TUDO PASSOU")
```

Reportar a saída literal. Um peso de teste fica lançado com a data de hoje — é dado real e plausível, mas avisar no relatório que ele existe, para o usuário poder corrigir com o peso de verdade.

- [ ] **Step 3: Rodar a suíte** → 57 passed.

---

## Task 8: Tipos e serviço no frontend

**Files:** Modify `frontend/src/app/core/models.ts`, Modify `frontend/src/app/core/api.service.ts`

- [ ] **Step 1: Tipos** — acrescentar ao final de `models.ts`:

```typescript
// --- Treinador -----------------------------------------------------------

export interface Readiness {
  state: 'sem_historico' | 'folga' | 'leve' | 'convite' | 'livre';
  severity: string;
  rides_needed: number;
  headline: string;
  detail: string;
}

export interface Prescription {
  kind: 'folga' | 'pedal' | 'bonus';
  minutes: number | null;
  zone: string | null;
  headline: string;
  detail: string;
}

export interface ConsistencyWeek {
  week: string;
  rides: number;
  minutes: number;
  met_goal: boolean;
}

export interface WeightProgress {
  current_kg: number;
  first_kg: number;
  change_kg: number;
  target_kg: number | null;
  series: { date: string; weight_kg: number }[];
}

export interface CoachGoal {
  rides_per_week: number;
  minutes_per_week: number;
  target_weight_kg: number | null;
}

export interface GoalSuggestion {
  minutes_per_week: number;
  rides_per_week: number;
  reason: string;
}

export interface Fitness {
  ctl: number;
  series: { date: string; ctl: number }[];
  depends_on_estimated_ftp: boolean;
}

export interface CoachReading {
  readiness: Readiness;
  prescription: Prescription;
  progress: {
    consistency: { weeks: ConsistencyWeek[]; goal_rides: number; goal_minutes: number };
    weight: WeightProgress | null;
    fitness: Fitness;
  };
  goal: CoachGoal;
  goal_suggestion: GoalSuggestion | null;
  ftp_is_default: boolean;
}

export interface WeightEntry {
  measured_on: string;
  weight_kg: number;
  note: string | null;
}
```

- [ ] **Step 2: Serviço** — acrescentar os tipos ao import e os métodos ao final de `ApiService`:

```typescript
  coach(): Observable<CoachReading> {
    return this.http.get<CoachReading>(this.base + '/coach');
  }

  setGoal(goal: CoachGoal): Observable<CoachGoal> {
    return this.http.put<CoachGoal>(this.base + '/coach/goal', goal);
  }

  weightLog(): Observable<WeightEntry[]> {
    return this.http.get<WeightEntry[]>(this.base + '/weight');
  }

  logWeight(measured_on: string, weight_kg: number): Observable<unknown> {
    return this.http.post(this.base + '/weight', { measured_on, weight_kg });
  }
```

- [ ] **Step 3:** `npx tsc --noEmit -p tsconfig.app.json` → limpo.

---

## Task 9: A aba Treinador

**Files:** Create `frontend/src/app/pages/coach.component.ts`, Modify `app.routes.ts`, Modify `app.component.ts`

- [ ] **Step 1: Criar o componente**

```typescript
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ChartConfiguration } from 'chart.js';
import { ApiService } from '../core/api.service';
import { CoachGoal, CoachReading } from '../core/models';
import { ChartComponent } from '../shared/chart.component';
import { NumPipe } from '../shared/format.pipe';

@Component({
  selector: 'app-coach',
  standalone: true,
  imports: [FormsModule, ChartComponent, NumPipe],
  template: `
    @if (data(); as d) {
      <section class="section">
        <div class="section-head">
          <h1>Treinador</h1>
          <span class="hint">{{ d.goal.rides_per_week }} pedais · {{ d.goal.minutes_per_week }} min por semana</span>
        </div>

        <!-- Prontidao: a leitura de hoje -->
        <div class="card ready">
          <span class="eyebrow">Hoje</span>
          <h2 class="big">{{ d.readiness.headline }}</h2>
          <p>{{ d.readiness.detail }}</p>
        </div>

        <!-- Prescricao -->
        <div class="card" style="margin-bottom:20px">
          <span class="eyebrow">Sugestão</span>
          <h2 class="big">{{ d.prescription.headline }}</h2>
          <p>{{ d.prescription.detail }}</p>
        </div>

        @if (d.goal_suggestion; as s) {
          <div class="notice">
            {{ s.reason }}
            <button class="btn" style="margin-left:12px" (click)="aceitarSugestao()">
              Subir para {{ s.minutes_per_week }} min
            </button>
          </div>
        }

        <!-- Progresso -->
        <div class="section-head" style="margin-top:32px">
          <h2>Progresso</h2>
          <span class="hint">constância primeiro — é dela que vem o resto</span>
        </div>

        <div class="grid cols-2">
          <div class="card">
            <h2>Constância</h2>
            <div class="chart-box">
              @if (consistencyChart(); as cfg) { <app-chart [config]="cfg" /> }
            </div>
          </div>
          <div class="card">
            <h2>Peso</h2>
            @if (d.progress.weight; as w) {
              <div class="grid cols-2" style="gap:12px; margin-bottom:14px">
                <div class="plate">
                  <span class="label">Agora</span>
                  <span class="value">{{ w.current_kg | num: 1 }}</span><span class="unit">kg</span>
                </div>
                <div class="plate">
                  <span class="label">Desde o início</span>
                  <span class="value">{{ w.change_kg | num: 1 }}</span><span class="unit">kg</span>
                </div>
              </div>
              <div class="chart-box" style="height:180px">
                @if (weightChart(); as cfg) { <app-chart [config]="cfg" /> }
              </div>
            } @else {
              <p class="hint">
                Nenhum peso registrado ainda. Lance o primeiro abaixo — ele destrava a linha de
                tendência e corrige o cálculo de potência, que hoje usa um valor fixo.
              </p>
            }
          </div>
        </div>

        <!-- Quarta linha: condicionamento, com a ressalva na propria tela -->
        <div class="card" style="margin-top:20px">
          <h2>Condicionamento</h2>
          <div class="grid cols-2" style="gap:12px">
            <div class="plate">
              <span class="label">Base (CTL)</span>
              <span class="value">{{ d.progress.fitness.ctl | num: 1 }}</span>
            </div>
            <p class="hint" style="margin:0; align-self:center">
              Sobe devagar com volume constante. Este número depende do seu FTP — e o seu está
              no valor padrão, então leia a <em>tendência</em>, não o valor.
            </p>
          </div>
        </div>

        <!-- Lancamentos -->
        <div class="card" style="margin-top:20px">
          <h2>Registrar</h2>
          <div class="linha">
            <label>Peso hoje (kg)<input type="number" step="0.1" [(ngModel)]="novoPeso" /></label>
            <button class="btn" (click)="lancarPeso()" [disabled]="!novoPeso">Lançar</button>
          </div>
          <div class="linha" style="margin-top:14px">
            <label>Pedais por semana<input type="number" [(ngModel)]="metaPedais" /></label>
            <label>Minutos por semana<input type="number" [(ngModel)]="metaMinutos" /></label>
            <button class="btn ghost" (click)="salvarMeta()">Salvar meta</button>
          </div>
        </div>

        @if (d.ftp_is_default) {
          <div class="notice" style="margin-top:20px">
            <strong>Sobre o gráfico de forma.</strong> Seu FTP está no valor padrão de 220 W, que
            ninguém mediu. CTL, ATL e TSB dependem dele — por isso este treinador fala em minutos e
            pedais, que não dependem de número nenhum estimado.
          </div>
        }
      </section>
    } @else {
      <p class="eyebrow">Carregando…</p>
    }
  `,
  styles: [
    `
      .ready { border-left: 3px solid var(--ink); margin-bottom: 20px; }
      .big { font-size: 1.6rem; text-transform: none; letter-spacing: 0; margin-bottom: 8px; }
      .linha { display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap; }
      .linha label {
        display: flex; flex-direction: column; gap: 4px;
        font-family: var(--mono); font-size: 0.65rem; letter-spacing: 0.12em;
        text-transform: uppercase; color: var(--graphite);
      }
      .linha input {
        font-family: var(--body); font-size: 0.95rem; text-transform: none; letter-spacing: 0;
        color: var(--ink); border: 1px solid var(--rule); border-radius: var(--radius);
        padding: 8px 10px; background: #fff; width: 140px;
      }
    `,
  ],
})
export class CoachComponent implements OnInit {
  private api = inject(ApiService);

  data = signal<CoachReading | null>(null);
  novoPeso: number | null = null;
  metaPedais = 3;
  metaMinutos = 180;

  ngOnInit(): void {
    this.carregar();
  }

  private carregar(): void {
    this.api.coach().subscribe((d) => {
      this.data.set(d);
      this.metaPedais = d.goal.rides_per_week;
      this.metaMinutos = d.goal.minutes_per_week;
    });
  }

  lancarPeso(): void {
    if (!this.novoPeso) {
      return;
    }
    const hoje = new Date().toISOString().slice(0, 10);
    this.api.logWeight(hoje, this.novoPeso).subscribe(() => {
      this.novoPeso = null;
      this.carregar();
    });
  }

  salvarMeta(): void {
    const goal: CoachGoal = {
      rides_per_week: this.metaPedais,
      minutes_per_week: this.metaMinutos,
      target_weight_kg: this.data()?.goal.target_weight_kg ?? null,
    };
    this.api.setGoal(goal).subscribe(() => this.carregar());
  }

  aceitarSugestao(): void {
    const s = this.data()?.goal_suggestion;
    if (!s) {
      return;
    }
    this.metaMinutos = s.minutes_per_week;
    this.metaPedais = s.rides_per_week;
    this.salvarMeta();
  }

  consistencyChart(): ChartConfiguration | null {
    const weeks = this.data()?.progress.consistency.weeks;
    if (!weeks?.length) {
      return null;
    }
    const meta = this.data()!.progress.consistency.goal_minutes;
    return {
      type: 'bar',
      data: {
        labels: weeks.map((w) => w.week.slice(5)),
        datasets: [
          {
            type: 'bar',
            label: 'minutos',
            data: weeks.map((w) => w.minutes),
            // Bateu a meta ganha tinta cheia; nao bateu fica esmaecido - sem
            // vermelho, que neste app significa frequencia cardiaca (SPEC 5).
            backgroundColor: weeks.map((w) => (w.met_goal ? '#0e1f2b' : 'rgba(14,31,43,0.30)')),
            borderRadius: 2,
          },
          {
            type: 'line',
            label: 'meta',
            data: weeks.map(() => meta),
            borderColor: '#64798a',
            borderDash: [4, 3],
            borderWidth: 1.5,
            pointRadius: 0,
          },
        ],
      },
      options: {
        scales: { y: { title: { display: true, text: 'minutos' } }, x: { grid: { display: false } } },
        plugins: { legend: { labels: { boxWidth: 10, boxHeight: 10 } } },
      },
    };
  }

  weightChart(): ChartConfiguration | null {
    const w = this.data()?.progress.weight;
    if (!w?.series?.length) {
      return null;
    }
    return {
      type: 'line',
      data: {
        labels: w.series.map((p) => p.date.slice(5)),
        datasets: [
          {
            label: 'kg',
            data: w.series.map((p) => p.weight_kg),
            borderColor: '#0e1f2b',
            backgroundColor: 'rgba(14,31,43,0.08)',
            fill: true,
            borderWidth: 2,
            pointRadius: 2,
            tension: 0.2,
          },
        ],
      },
      options: { plugins: { legend: { display: false } } },
    };
  }
}
```

- [ ] **Step 2: Rota** — em `app.routes.ts`, antes da rota `treinos`:

```typescript
  { path: 'treinador', loadComponent: () => import('./pages/coach.component').then((m) => m.CoachComponent) },
```

- [ ] **Step 3: Menu** — em `app.component.ts`, depois do link de Evolução:

```html
          <a routerLink="/treinador" routerLinkActive="active">Treinador</a>
```

- [ ] **Step 4:** `npx tsc --noEmit -p tsconfig.app.json` → limpo.

---

## Task 10: Verificação fim a fim

- [ ] **Step 1: Suíte completa**

```bash
cd "d:/AI Solution/Bike_Graph/backend"
./.venv/Scripts/python.exe -m pytest tests/ -q
```

Esperado: 57 passed.

- [ ] **Step 2: Endpoints** (o controlador reinicia o backend antes)

```bash
for ep in "/api/coach" "/api/coach/goal" "/api/weight"; do
  printf "  %s  %s\n" "$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:4200$ep")" "$ep"
done
```

Esperado: 200 nos três.

- [ ] **Step 3: Na tela**

Abrir `http://localhost:4200/treinador` e conferir:

| O que | Esperado |
|---|---|
| Prontidão | "Ainda não tenho histórico pra ler" — com 1 treino no banco é o correto |
| Prescrição | Uma sugestão de duração em ritmo de conversa |
| Constância | Uma barra, esmaecida (não bateu a meta) |
| Peso | Texto convidando a lançar o primeiro |
| Aviso de FTP | Presente, porque o FTP é o default de 220 |
| Lançar peso | Salva e o gráfico aparece |
| Salvar meta | Persiste e o cabeçalho atualiza |
