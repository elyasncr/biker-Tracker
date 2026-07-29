# Transmissão declarada e cobertura de marchas — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Declarar coroas, catraca e aro de cada bike, e cruzar isso com o desenvolvimento medido no treino para mostrar quais faixas de marcha ficaram paradas.

**Architecture:** Um módulo novo e isolado (`services/drivetrain.py`) concentra toda a matemática da máquina — tabela de relações, agrupamento de colisões, contagem de cobertura. Ele não conhece treino nem banco. O router de análise compõe: chama `analysis.analyze()` como hoje e, quando a bike do treino tem transmissão declarada, anexa `gears.coverage`. O frontend troca o histograma de faixas arbitrárias por um gráfico de uma barra por relação.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0, numpy, pytest (novo). Angular 19 standalone, Chart.js 4.

**Spec:** `docs/superpowers/specs/2026-07-29-garagem-transmissao-design.md`

> ⚠️ **DECISÃO DO USUÁRIO: este projeto não usa git.**
> **Pule a Task 0 inteira e TODO passo de commit** (`git add` / `git commit`) das demais
> tarefas. Não rode `git init`. Todo o resto do plano — código, testes e verificações — vale
> normalmente. Um snapshot manual dos arquivos originais foi guardado no scratchpad da sessão
> antes de começar, e é o único ponto de retorno que existe.

---

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `backend/app/services/drivetrain.py` | **Criar.** Matemática da transmissão: presets, tabela de relações, colisões, cobertura. Sem banco, sem I/O. |
| `backend/tests/test_drivetrain.py` | **Criar.** Primeiro conjunto de testes do projeto. |
| `backend/app/models.py` | **Modificar.** `chainrings` e `cassette` na `Bike`. |
| `backend/app/routers/bikes.py` | **Modificar.** `BikeUpdate` opcional (conserta o PATCH-que-é-PUT) e campos novos. |
| `backend/app/routers/activities.py` | **Modificar.** Aceitar `bike_id` no PATCH. |
| `backend/app/routers/analysis.py` | **Modificar.** Compor `gears.coverage`. |
| `backend/app/services/analysis.py` | **Modificar.** `sample_rate_of()` público; `gear_report` usa `drivetrain.development()`. |
| `backend/requirements.txt` | **Modificar.** `pytest`. |
| `frontend/src/app/core/models.ts` | **Modificar.** Tipos de transmissão e cobertura. |
| `frontend/src/app/core/api.service.ts` | **Modificar.** `updateBike()`, `updateActivity()`. |
| `frontend/src/app/pages/bikes.component.ts` | **Modificar.** Seção Transmissão com presets. |
| `frontend/src/app/shared/telemetry-panel.component.ts` | **Modificar.** Gráfico de cobertura. |
| `frontend/src/app/pages/activity-detail.component.ts` | **Modificar.** Seletor de bike. |

---

## Task 0: Rede de segurança — controle de versão

O projeto não tem `.git`. Vamos tocar em 13 arquivos, incluindo o `analysis.py` que a SPEC marca como território sensível. Sem isso não existe como desfazer.

**Files:**
- Create: `.gitignore` (substitui o atual, que só cobre Node)

- [ ] **Step 1: Escrever o `.gitignore` completo**

```gitignore
# Node / Angular
node_modules/
dist/
.angular/

# Python
.venv/
venv/
__pycache__/
*.py[cod]
.pytest_cache/

# Segredos e dados locais
.env
*.db

# Treinos: o .fit e seu, nao do repositorio
data/*.fit
```

- [ ] **Step 2: Inicializar o repositório e gravar o estado atual**

```bash
cd "d:/AI Solution/Bike_Graph"
git init
git add -A
git status --short
```

Esperado: nenhum `.env`, nenhum `igpsport.db`, nenhum `.fit`, nenhum `node_modules/` na lista.

- [ ] **Step 3: Commit do baseline**

```bash
git commit -m "chore: estado inicial do projeto antes da feature de transmissao"
```

---

## Task 1: `drivetrain.py` — desenvolvimento e tabela de relações

**Files:**
- Create: `backend/app/services/drivetrain.py`
- Create: `backend/tests/test_drivetrain.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Adicionar pytest ao requirements**

Em `backend/requirements.txt`, acrescentar ao final:

```
pytest==8.3.4
```

Instalar:

```bash
cd "d:/AI Solution/Bike_Graph/backend"
./.venv/Scripts/python.exe -m pip install pytest==8.3.4
```

- [ ] **Step 2: Escrever o teste que falha**

Criar `backend/tests/test_drivetrain.py`:

```python
"""Testes da matematica de transmissao.

Fixture principal: a Rockrider ST100 2022 do usuario - 3x7, coroas 42-34-24,
catraca 14-34, aro 29x2.1 (2288 mm). Bike real em vez de exemplo de manual.
"""

import numpy as np
import pytest

from app.services import drivetrain

ST100_CHAINRINGS = [42, 34, 24]
ST100_CASSETTE = [14, 16, 18, 20, 24, 28, 34]
ST100_WHEEL_MM = 2288


def test_gear_table_gera_todas_as_combinacoes():
    gears = drivetrain.gear_table(ST100_CHAINRINGS, ST100_CASSETTE, ST100_WHEEL_MM)
    assert len(gears) == 21  # 3 coroas x 7 cogs


def test_gear_table_calcula_desenvolvimento_correto():
    gears = drivetrain.gear_table(ST100_CHAINRINGS, ST100_CASSETTE, ST100_WHEEL_MM)
    by_name = {g.name: g for g in gears}
    # 34/18 x 2.288 m = 4.3217...
    assert by_name["34x18"].development_m == pytest.approx(4.322, abs=0.001)
    assert by_name["42x14"].development_m == pytest.approx(6.864, abs=0.001)
    assert by_name["24x34"].development_m == pytest.approx(1.615, abs=0.001)


def test_gear_table_vem_ordenada_por_desenvolvimento():
    gears = drivetrain.gear_table(ST100_CHAINRINGS, ST100_CASSETTE, ST100_WHEEL_MM)
    valores = [g.development_m for g in gears]
    assert valores == sorted(valores)


def test_gear_table_sem_transmissao_devolve_lista_vazia():
    assert drivetrain.gear_table([], ST100_CASSETTE, ST100_WHEEL_MM) == []
    assert drivetrain.gear_table(ST100_CHAINRINGS, [], ST100_WHEEL_MM) == []
    assert drivetrain.gear_table(ST100_CHAINRINGS, ST100_CASSETTE, None) == []


def test_development_e_a_volta_da_conta():
    # A 70 rpm na 34x18 (4.322 m por pedalada), a bike anda 4.322 * 70 m/min.
    esperado_kmh = 4.322 * 70 * 60 / 1000
    cadence = np.array([70.0])
    speed = np.array([esperado_kmh])
    assert drivetrain.development(cadence, speed)[0] == pytest.approx(4.322, abs=0.01)
```

- [ ] **Step 3: Rodar o teste e confirmar que falha**

```bash
cd "d:/AI Solution/Bike_Graph/backend"
./.venv/Scripts/python.exe -m pytest tests/test_drivetrain.py -v
```

Esperado: FAIL — `ModuleNotFoundError: No module named 'app.services.drivetrain'`

- [ ] **Step 4: Implementar o mínimo**

Criar `backend/app/services/drivetrain.py`:

```python
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


@dataclass(frozen=True)
class Gear:
    """Uma combinacao mecanica: coroa x cog, e quanto ela anda por pedalada."""

    development_m: float
    chainring: int
    cog: int

    @property
    def name(self) -> str:
        return f"{self.chainring}x{self.cog}"


def development(cadence: np.ndarray, speed_kmh: np.ndarray) -> np.ndarray:
    """Metros que a bike anda a cada volta completa do pedal.

    E a conta que revela a marcha sem nenhum sensor a mais. Casa canonica da
    formula: o analysis.gear_report() importa daqui em vez de manter copia.
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        return (speed_kmh / 3.6) * 60 / cadence


def gear_table(chainrings, cassette, wheel_mm) -> list[Gear]:
    """Todas as combinacoes mecanicas da bike, ordenadas por desenvolvimento."""
    if not chainrings or not cassette or not wheel_mm:
        return []
    wheel_m = wheel_mm / 1000
    gears = [
        Gear(round(int(ring) / int(cog) * wheel_m, 4), int(ring), int(cog))
        for ring, cog in product(chainrings, cassette)
    ]
    return sorted(gears, key=lambda g: g.development_m)
```

- [ ] **Step 5: Rodar os testes e confirmar que passam**

```bash
cd "d:/AI Solution/Bike_Graph/backend"
./.venv/Scripts/python.exe -m pytest tests/test_drivetrain.py -v
```

Esperado: 5 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/drivetrain.py backend/tests/test_drivetrain.py backend/requirements.txt
git commit -m "feat(drivetrain): tabela de relacoes e desenvolvimento, com os primeiros testes do projeto"
```

---

## Task 2: `collapse()` — agrupar relações indistinguíveis

**Files:**
- Modify: `backend/app/services/drivetrain.py`
- Modify: `backend/tests/test_drivetrain.py`

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar em `backend/tests/test_drivetrain.py`:

```python
def test_collapse_agrupa_relacoes_identicas():
    gears = drivetrain.gear_table(ST100_CHAINRINGS, ST100_CASSETTE, ST100_WHEEL_MM)
    groups = drivetrain.collapse(gears)
    # 24x24 e 34x34 dao exatamente o mesmo desenvolvimento (2.288 m)
    grupo = next(g for g in groups if "24x24" in g.label)
    assert "34x34" in grupo.label


def test_collapse_reduz_21_combinacoes_a_14_faixas():
    gears = drivetrain.gear_table(ST100_CHAINRINGS, ST100_CASSETTE, ST100_WHEEL_MM)
    groups = drivetrain.collapse(gears)
    assert len(groups) == 14
    assert sum(len(g.gears) for g in groups) == 21  # nenhuma marcha se perde


def test_collapse_nao_agrupa_o_que_e_distinguivel():
    gears = drivetrain.gear_table(ST100_CHAINRINGS, ST100_CASSETTE, ST100_WHEEL_MM)
    groups = drivetrain.collapse(gears)
    # 34x18 (4.322) esta a 8% da vizinha - tem faixa so dela
    grupo = next(g for g in groups if "34x18" in g.label)
    assert len(grupo.gears) == 1


def test_collapse_em_1x_nunca_agrupa():
    gears = drivetrain.gear_table([32], [11, 13, 15, 17, 19, 22, 25, 28, 32, 36, 42], 2288)
    groups = drivetrain.collapse(gears)
    assert len(groups) == 11
    assert all(len(g.gears) == 1 for g in groups)


def test_collapse_centro_do_grupo_e_a_media():
    gears = drivetrain.gear_table(ST100_CHAINRINGS, ST100_CASSETTE, ST100_WHEEL_MM)
    groups = drivetrain.collapse(gears)
    grupo = next(g for g in groups if len(g.gears) > 1)
    esperado = sum(x.development_m for x in grupo.gears) / len(grupo.gears)
    assert grupo.development_m == pytest.approx(esperado, abs=0.001)


def test_collapse_lista_vazia():
    assert drivetrain.collapse([]) == []
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_drivetrain.py -v
```

Esperado: FAIL — `AttributeError: module 'app.services.drivetrain' has no attribute 'collapse'`

- [ ] **Step 3: Implementar**

Acrescentar em `backend/app/services/drivetrain.py`, depois de `Gear`:

```python
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
```

E a função, depois de `gear_table()`:

```python
def collapse(gears: list[Gear], tolerance_pct: float = COLLISION_PCT) -> list[GearGroup]:
    """Junta relacoes cujo desenvolvimento a medicao nao separa."""
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
```

- [ ] **Step 4: Rodar e confirmar que passam**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_drivetrain.py -v
```

Esperado: 11 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/drivetrain.py backend/tests/test_drivetrain.py
git commit -m "feat(drivetrain): agrupa relacoes indistinguiveis por limiar relativo de 4%"
```

---

## Task 3: `coverage()` — quanto tempo em cada faixa

**Files:**
- Modify: `backend/app/services/drivetrain.py`
- Modify: `backend/tests/test_drivetrain.py`

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar em `backend/tests/test_drivetrain.py`:

```python
def _pedal_sintetico(desenvolvimentos, amostras_por_marcha=40, cadencia=70.0):
    """Monta cadencia/velocidade que produzem exatamente os desenvolvimentos dados."""
    cad, spd = [], []
    for dev in desenvolvimentos:
        for _ in range(amostras_por_marcha):
            cad.append(cadencia)
            spd.append(dev * cadencia * 60 / 1000)  # m/pedalada -> km/h
    return np.array(cad), np.array(spd)


def _grupos_st100():
    return drivetrain.collapse(
        drivetrain.gear_table(ST100_CHAINRINGS, ST100_CASSETTE, ST100_WHEEL_MM)
    )


def test_coverage_conta_o_tempo_na_faixa_certa():
    groups = _grupos_st100()
    cad, spd = _pedal_sintetico([4.322], amostras_por_marcha=100)  # so 34x18
    result = drivetrain.coverage(cad, spd, groups, sample_rate_s=1.0)
    banda = next(b for b in result["bands"] if b["label"] == "34x18")
    assert banda["seconds"] == 100
    assert banda["used"] is True


def test_coverage_marca_faixa_vazia_como_nao_usada():
    groups = _grupos_st100()
    cad, spd = _pedal_sintetico([4.322], amostras_por_marcha=100)
    result = drivetrain.coverage(cad, spd, groups, sample_rate_s=1.0)
    banda = next(b for b in result["bands"] if b["label"] == "24x34")
    assert banda["seconds"] == 0
    assert banda["used"] is False
    assert result["bands_used"] == 1
    assert result["bands_total"] == 14


def test_coverage_manda_o_que_nao_casa_para_o_balde_fora():
    groups = _grupos_st100()
    # 8.0 m nao existe nesta transmissao (a mais dura e 6.864)
    cad, spd = _pedal_sintetico([8.0], amostras_por_marcha=100)
    result = drivetrain.coverage(cad, spd, groups, sample_rate_s=1.0)
    assert result["off_gear_seconds"] == 100
    assert result["off_gear_ratio"] == pytest.approx(1.0)
    assert result["bands_used"] == 0


def test_coverage_respeita_a_taxa_de_amostragem():
    groups = _grupos_st100()
    cad, spd = _pedal_sintetico([4.322], amostras_por_marcha=100)
    um_hz = drivetrain.coverage(cad, spd, groups, sample_rate_s=1.0)
    sete_s = drivetrain.coverage(cad, spd, groups, sample_rate_s=7.0)
    a = next(b for b in um_hz["bands"] if b["label"] == "34x18")["seconds"]
    b = next(x for x in sete_s["bands"] if x["label"] == "34x18")["seconds"]
    assert b == a * 7


def test_coverage_ignora_amostra_parada_ou_sem_cadencia():
    groups = _grupos_st100()
    cad = np.array([70.0] * 100 + [0.0] * 50 + [np.nan] * 50)
    spd = np.array([4.322 * 70 * 60 / 1000] * 100 + [0.0] * 50 + [20.0] * 50)
    result = drivetrain.coverage(cad, spd, groups, sample_rate_s=1.0)
    total = sum(b["seconds"] for b in result["bands"]) + result["off_gear_seconds"]
    assert total == 100  # so as 100 amostras pedalando entraram


def test_coverage_avisa_quando_muita_coisa_cai_fora():
    groups = _grupos_st100()
    cad, spd = _pedal_sintetico([4.322, 8.0], amostras_por_marcha=100)
    result = drivetrain.coverage(cad, spd, groups, sample_rate_s=1.0)
    assert result["off_gear_ratio"] > drivetrain.OFF_GEAR_WARN
    assert "catraca" in result["insight"]


def test_coverage_sem_grupos_devolve_none():
    cad, spd = _pedal_sintetico([4.322])
    assert drivetrain.coverage(cad, spd, [], sample_rate_s=1.0) is None


def test_coverage_com_poucas_amostras_devolve_none():
    groups = _grupos_st100()
    cad, spd = _pedal_sintetico([4.322], amostras_por_marcha=10)
    assert drivetrain.coverage(cad, spd, groups, sample_rate_s=1.0) is None
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_drivetrain.py -v
```

Esperado: FAIL — `AttributeError: ... has no attribute 'coverage'`

- [ ] **Step 3: Implementar**

Acrescentar ao final de `backend/app/services/drivetrain.py`:

```python
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
```

- [ ] **Step 4: Rodar e confirmar que passam**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_drivetrain.py -v
```

Esperado: 19 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/drivetrain.py backend/tests/test_drivetrain.py
git commit -m "feat(drivetrain): relatorio de cobertura com balde fora-de-relacao"
```

---

## Task 4: Catálogo de presets

**Files:**
- Modify: `backend/app/services/drivetrain.py`
- Modify: `backend/tests/test_drivetrain.py`
- Modify: `backend/app/routers/bikes.py`

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar em `backend/tests/test_drivetrain.py`:

```python
def test_presets_tem_as_tres_familias():
    assert set(drivetrain.PRESETS) == {"chainrings", "cassettes", "wheels"}


def test_presets_produzem_transmissoes_validas():
    for preset in drivetrain.PRESETS["chainrings"]:
        assert preset["value"], preset["label"]
        assert all(20 <= d <= 60 for d in preset["value"]), preset["label"]
    for preset in drivetrain.PRESETS["cassettes"]:
        assert all(9 <= d <= 52 for d in preset["value"]), preset["label"]
        assert preset["value"] == sorted(preset["value"]), preset["label"]
    for preset in drivetrain.PRESETS["wheels"]:
        assert 1000 <= preset["value"] <= 2400, preset["label"]


def test_preset_da_st100_existe_e_bate_com_a_bike_real():
    coroa = next(p for p in drivetrain.PRESETS["chainrings"] if p["value"] == [42, 34, 24])
    catraca = next(p for p in drivetrain.PRESETS["cassettes"] if p["value"] == ST100_CASSETTE)
    aro = next(p for p in drivetrain.PRESETS["wheels"] if p["value"] == 2288)
    assert "42" in coroa["label"] and "14" in catraca["label"] and "29" in aro["label"]
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_drivetrain.py -v
```

Esperado: FAIL — `AttributeError: ... has no attribute 'PRESETS'`

- [ ] **Step 3: Implementar**

Acrescentar ao final de `backend/app/services/drivetrain.py`:

```python
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
```

- [ ] **Step 4: Expor os presets pela API**

Em `backend/app/routers/bikes.py`, acrescentar o import no topo:

```python
from ..services import drivetrain
```

E a rota, logo depois de `list_bikes()`:

```python
@router.get("/drivetrain-presets")
def drivetrain_presets():
    """Catalogo de coroas, catracas e aros para o formulario da Garagem."""
    return drivetrain.PRESETS
```

- [ ] **Step 5: Rodar os testes e conferir a rota**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_drivetrain.py -v
curl -s http://localhost:8000/api/bikes/drivetrain-presets | head -c 200
```

Esperado: 22 passed; o curl devolve JSON com `chainrings`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/drivetrain.py backend/tests/test_drivetrain.py backend/app/routers/bikes.py
git commit -m "feat(drivetrain): catalogo de presets exposto pela API"
```

---

## Task 5: Colunas `chainrings` e `cassette` na Bike

**Files:**
- Modify: `backend/app/models.py`
- Modify: `README.md`

- [ ] **Step 1: Acrescentar as colunas**

Em `backend/app/models.py`, na classe `Bike`, logo depois de `wheel_circumference_mm`:

```python
    # Transmissao declarada. Guardamos a LISTA DE DENTES, nao o nome do preset:
    # duas fontes de verdade acabam divergindo, e e a lista que entra na conta.
    chainrings: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [42, 34, 24]
    cassette: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [14, 16, ..., 34]
```

- [ ] **Step 2: Recriar o banco**

O projeto usa `Base.metadata.create_all()`, que **cria tabela que falta mas não altera tabela existente**. Coluna nova em banco já criado não aparece sozinha.

```bash
cd "d:/AI Solution/Bike_Graph/backend"
# derrubar o uvicorn antes (Ctrl+C na janela dele), senao o Windows segura o arquivo
rm -f igpsport.db
./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
```

O banco é reconstruível: o boot varre `data/` e reimporta tudo.

- [ ] **Step 3: Reconferir que o treino voltou**

```bash
curl -s http://localhost:8000/api/activities | head -c 120
```

Esperado: o pedal de 27/07 de volta. A bike some — recadastrar no Step 4.

- [ ] **Step 4: Recadastrar a Rockrider, agora com transmissão**

```bash
curl -s -X POST http://localhost:8000/api/bikes -H "Content-Type: application/json" -d '{
  "name": "Rockrider ST100", "brand": "Rockrider", "model": "ST100", "year": 2022,
  "kind": "mtb", "weight_kg": 15.4, "wheel_circumference_mm": 2288,
  "chainrings": [42, 34, 24], "cassette": [14, 16, 18, 20, 24, 28, 34],
  "is_default": true
}'
curl -s -X POST "http://localhost:8000/api/sync?force=true"
```

Nota: o POST só vai aceitar `chainrings`/`cassette` depois da Task 6. Rodar este step de novo ao final dela.

- [ ] **Step 5: Documentar no README**

Em `README.md`, ao final da seção "Ajuste isto antes de olhar os números", acrescentar:

```markdown
**Sobre colunas novas no banco:** o SQLAlchemy cria tabela que falta, mas não altera tabela
existente. Se você atualizar o código e aparecer erro de coluna inexistente, apague
`backend/igpsport.db` e suba de novo — o banco é reconstruído varrendo `data/`.
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/models.py README.md
git commit -m "feat(bikes): colunas chainrings e cassette"
```

---

## Task 6: Consertar o PATCH de bikes e aceitar a transmissão

O `PATCH /api/bikes/{id}` de hoje faz `setattr` de todos os campos do `BikeInput`, e todos têm default `None`. Editar só a catraca apagaria marca, modelo, ano, peso e aro, e resetaria `kind` para `"speed"`. Isso deixa de ser defeito latente e vira bloqueio: o fluxo previsto é cadastrar a bike, contar os dentes e voltar pra editar.

**Files:**
- Modify: `backend/app/routers/bikes.py:15-27` (schema), `:51-74` (POST e PATCH)

- [ ] **Step 1: Trocar os schemas**

Em `backend/app/routers/bikes.py`, substituir a classe `BikeInput` inteira por:

```python
class BikeInput(BaseModel):
    """Corpo do POST: cria uma bike. So o nome e obrigatorio."""

    name: str
    crr: float | None = None
    cda: float | None = None
    brand: str | None = None
    model: str | None = None
    year: int | None = None
    kind: str = "speed"
    weight_kg: float | None = None
    wheel_circumference_mm: int | None = None
    chainrings: list[int] | None = None
    cassette: list[int] | None = None
    notes: str | None = None
    is_default: bool = False

    @field_validator("chainrings")
    @classmethod
    def _coroas_validas(cls, v):
        if v is not None and not all(20 <= d <= 60 for d in v):
            raise ValueError("Coroa fora da faixa util (20 a 60 dentes)")
        return sorted(v, reverse=True) if v else v

    @field_validator("cassette")
    @classmethod
    def _cogs_validos(cls, v):
        if v is not None and not all(9 <= d <= 52 for d in v):
            raise ValueError("Cog fora da faixa util (9 a 52 dentes)")
        return sorted(v) if v else v

    @field_validator("wheel_circumference_mm")
    @classmethod
    def _aro_valido(cls, v):
        # Faixa util: 1000 mm cobre roda de 16", 2400 cobre 29" com pneu gordo.
        # Fora disso o mapa de marchas inteiro sai deslocado, sem aviso nenhum.
        if v is not None and not 1000 <= v <= 2400:
            raise ValueError("Circunferencia fora da faixa util (1000 a 2400 mm)")
        return v


class BikeUpdate(BikeInput):
    """Corpo do PATCH: TUDO opcional.

    Sem isso o PATCH se comporta como PUT - manda so a catraca e apaga marca,
    modelo, ano, peso e aro, porque todo campo ausente vira None e o setattr
    grava esse None por cima. Quem edita um campo nao espera perder os outros.
    """

    name: str | None = None
    kind: str | None = None
    is_default: bool | None = None
```

E acrescentar `field_validator` ao import do pydantic no topo:

```python
from pydantic import BaseModel, field_validator
```

- [ ] **Step 2: Trocar o PATCH inteiro**

Substituir a função `update_bike()` completa por:

```python
@router.patch("/{bike_id}")
def update_bike(bike_id: int, payload: BikeUpdate, db: Session = Depends(get_db)):
    bike = db.get(Bike, bike_id)
    if bike is None:
        raise HTTPException(404, "Bike nao encontrada")

    # exclude_unset e o coracao do conserto: so grava o que o cliente REALMENTE
    # mandou. Sem ele, todo campo ausente vira None e o setattr apaga o que ja
    # estava la - mandar so a catraca zerava marca, modelo, ano, peso e aro.
    dados = payload.model_dump(exclude_unset=True)

    if dados.get("is_default"):
        for other in db.scalars(select(Bike).where(Bike.is_default.is_(True), Bike.id != bike_id)):
            other.is_default = False

    for key, value in dados.items():
        setattr(bike, key, value)

    db.commit()
    return {"id": bike.id, "name": bike.name}
```

- [ ] **Step 3: Devolver a transmissão no GET**

Em `list_bikes()`, acrescentar ao dicionário de cada bike, depois de `"weight_kg"`:

```python
                "wheel_circumference_mm": bike.wheel_circumference_mm,
                "chainrings": bike.chainrings,
                "cassette": bike.cassette,
```

- [ ] **Step 4: Verificar que o PATCH parou de apagar**

```bash
curl -s -X POST http://localhost:8000/api/bikes -H "Content-Type: application/json" \
  -d '{"name":"Teste","brand":"Marca","model":"Modelo","year":2020,"kind":"mtb","weight_kg":14.0}'
# supondo id 2:
curl -s -X PATCH http://localhost:8000/api/bikes/2 -H "Content-Type: application/json" \
  -d '{"cassette":[14,16,18,20,24,28,34]}'
curl -s http://localhost:8000/api/bikes
```

Esperado: a bike "Teste" mantém marca, modelo, ano, `kind: "mtb"` e peso 14,0 — e ganha a catraca. Antes do conserto, tudo isso viraria `null` e `kind` voltaria a `"speed"`.

```bash
curl -s -X DELETE http://localhost:8000/api/bikes/2   # limpar
```

- [ ] **Step 5: Rodar o Step 4 da Task 5 (recadastrar a Rockrider com transmissão)**

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/bikes.py
git commit -m "fix(bikes): PATCH deixa de apagar campos ausentes; aceita transmissao"
```

---

## Task 7: Ligar a cobertura na rota de análise

**Files:**
- Modify: `backend/app/services/analysis.py`
- Modify: `backend/app/routers/analysis.py:13-23`

- [ ] **Step 1: Expor a taxa de amostragem e usar a fórmula canônica**

Em `backend/app/services/analysis.py`, acrescentar logo depois de `effective_sample_rate()`:

```python
def sample_rate_of(streams: dict) -> float:
    """Taxa efetiva de amostragem da serie guardada, a partir do dicionario cru."""
    return effective_sample_rate(_arr(streams.get("t"), len(streams.get("t") or [])))
```

No mesmo arquivo, acrescentar ao import no topo:

```python
from . import drivetrain
```

E em `gear_report()`, trocar a linha que calcula o desenvolvimento:

```python
    development = (kmh / 3.6) * 60 / rpm  # metros por volta da pedivela
```

por:

```python
    # Formula canonica mora no drivetrain: e conta de maquina, nao de pedal.
    development = drivetrain.development(rpm, kmh)
```

Atenção à ordem dos argumentos: `drivetrain.development(cadence, speed_kmh)`.

- [ ] **Step 2: Compor a cobertura no router**

Em `backend/app/routers/analysis.py`, acrescentar ao import:

```python
from ..services import analysis, drivetrain
```

E substituir o corpo de `activity_analysis()` por:

```python
@router.get("/{activity_id}/analysis")
def activity_analysis(activity_id: int, db: Session = Depends(get_db)):
    """Telemetria do pedal: melhor e pior trecho, com o motivo de cada um."""
    activity = db.get(Activity, activity_id)
    if activity is None:
        raise HTTPException(404, "Treino nao encontrado")
    if activity.stream is None:
        raise HTTPException(422, "Esse treino nao tem serie temporal guardada.")

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
```

- [ ] **Step 3: Conferir que nada regrediu e que a cobertura chegou**

```bash
cd "d:/AI Solution/Bike_Graph/backend"
./.venv/Scripts/python.exe -m pytest tests/ -v
# reiniciar o uvicorn, depois:
curl -s http://localhost:8000/api/activities/1/analysis | ./.venv/Scripts/python.exe -c "
import json,sys
c=json.load(sys.stdin)['gears']['coverage']
print('bands_used ', c['bands_used'], 'de', c['bands_total'])
print('off_ratio  ', c['off_gear_ratio'])
for b in c['bands']:
    print(f\"  {b['development_m']:5.2f}  {b['label']:28s} {b['seconds']//60:3d} min  {'' if b['used'] else '<- NAO USADA'}\")
"
```

Esperado, conforme o teste de aceitação do spec §11: `bands_used 13 de 14`, `off_ratio ~0.15`, e `24x34` como única faixa parada.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/analysis.py backend/app/routers/analysis.py
git commit -m "feat(analise): anexa cobertura de marchas quando a bike tem transmissao declarada"
```

---

## Task 8: `bike_id` no PATCH de atividades

**Files:**
- Modify: `backend/app/routers/activities.py:51-62`

- [ ] **Step 1: Aceitar o campo**

Em `backend/app/routers/activities.py`, substituir `update_activity()` por:

```python
@router.patch("/{activity_id}", response_model=ActivitySummary)
def update_activity(
    activity_id: int,
    title: str | None = None,
    notes: str | None = None,
    bike_id: int | None = None,
    db: Session = Depends(get_db),
):
    activity = db.get(Activity, activity_id)
    if activity is None:
        raise HTTPException(404, "Treino nao encontrado")
    if title is not None:
        activity.title = title
    if notes is not None:
        activity.notes = notes
    if bike_id is not None:
        # bike_id = 0 desatribui: e o unico jeito de dizer "nenhuma" por query string,
        # onde ausente e None e ja significa "nao mexe".
        if bike_id == 0:
            activity.bike_id = None
        else:
            if db.get(Bike, bike_id) is None:
                raise HTTPException(404, "Bike nao encontrada")
            activity.bike_id = bike_id
    db.commit()
    db.refresh(activity)
    payload = ActivitySummary.model_validate(activity)
    payload.bike_name = activity.bike.name if activity.bike else None
    return payload
```

E acrescentar `Bike` ao import de models no topo:

```python
from ..models import Activity, Bike
```

- [ ] **Step 2: Verificar**

```bash
curl -s -X PATCH "http://localhost:8000/api/activities/1?bike_id=1" | head -c 200
curl -s -X PATCH "http://localhost:8000/api/activities/1?bike_id=999"
```

Esperado: o primeiro devolve o treino com `bike_name: "Rockrider ST100"`; o segundo devolve 404 "Bike nao encontrada".

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/activities.py
git commit -m "feat(activities): PATCH aceita bike_id"
```

---

## Task 9: Tipos e serviço no frontend

**Files:**
- Modify: `frontend/src/app/core/models.ts:184-191` (GearReport), `:245-259` (Bike)
- Modify: `frontend/src/app/core/api.service.ts`

- [ ] **Step 1: Acrescentar os tipos**

Em `frontend/src/app/core/models.ts`, acrescentar antes de `GearReport`:

```typescript
export interface CoverageBand {
  development_m: number;
  gears: string[];
  label: string;
  seconds: number;
  used: boolean;
}

export interface GearCoverage {
  bands: CoverageBand[];
  off_gear_seconds: number;
  off_gear_ratio: number;
  bands_used: number;
  bands_total: number;
  insight: string;
}

export interface DrivetrainPresets {
  chainrings: { label: string; value: number[] }[];
  cassettes: { label: string; value: number[] }[];
  wheels: { label: string; value: number }[];
}
```

Acrescentar em `GearReport`, depois de `insight?: string;`:

```typescript
  coverage?: GearCoverage;
```

Acrescentar em `Bike`, depois de `cda: number | null;`:

```typescript
  wheel_circumference_mm: number | null;
  chainrings: number[] | null;
  cassette: number[] | null;
```

- [ ] **Step 2: Acrescentar os métodos do serviço**

Em `frontend/src/app/core/api.service.ts`, acrescentar `DrivetrainPresets` ao import de `./models` e os métodos depois de `createBike()`:

```typescript
  updateBike(id: number, payload: Partial<Bike>): Observable<{ id: number; name: string }> {
    return this.http.patch<{ id: number; name: string }>(this.base + '/bikes/' + id, payload);
  }

  drivetrainPresets(): Observable<DrivetrainPresets> {
    return this.http.get<DrivetrainPresets>(this.base + '/bikes/drivetrain-presets');
  }

  updateActivity(id: number, changes: { bike_id?: number }): Observable<ActivitySummary> {
    let params = new HttpParams();
    if (changes.bike_id !== undefined) {
      params = params.set('bike_id', changes.bike_id);
    }
    return this.http.patch<ActivitySummary>(this.base + '/activities/' + id, null, { params });
  }
```

- [ ] **Step 3: Conferir que compila**

```bash
cd "d:/AI Solution/Bike_Graph/frontend"
npx tsc --noEmit -p tsconfig.app.json
```

Esperado: sem erros.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/core/models.ts frontend/src/app/core/api.service.ts
git commit -m "feat(frontend): tipos e chamadas de transmissao e cobertura"
```

---

## Task 10: Seção Transmissão na Garagem

**Files:**
- Modify: `frontend/src/app/pages/bikes.component.ts`

- [ ] **Step 1: Acrescentar o bloco no formulário**

Em `frontend/src/app/pages/bikes.component.ts`, no template, logo depois do `<label>` do CdA e antes do `<label class="check">`:

```html
          <label>
            Coroa
            <select [ngModel]="coroaPreset()" (ngModelChange)="aplicarCoroa($event)">
              <option [ngValue]="null">— escolha —</option>
              @for (p of presets()?.chainrings ?? []; track p.label) {
                <option [ngValue]="p.label">{{ p.label }}</option>
              }
            </select>
          </label>
          <label>
            Catraca
            <select [ngModel]="catracaPreset()" (ngModelChange)="aplicarCatraca($event)">
              <option [ngValue]="null">— escolha —</option>
              @for (p of presets()?.cassettes ?? []; track p.label) {
                <option [ngValue]="p.label">{{ p.label }}</option>
              }
            </select>
          </label>
          <label>
            Aro / pneu
            <select [ngModel]="aroPreset()" (ngModelChange)="aplicarAro($event)">
              <option [ngValue]="null">— escolha —</option>
              @for (p of presets()?.wheels ?? []; track p.label) {
                <option [ngValue]="p.label">{{ p.label }} ({{ p.value }} mm)</option>
              }
            </select>
          </label>
          <label class="check" style="grid-column: span 3">
            <span class="dentes">
              @if (draft.chainrings?.length) { Coroas: {{ draft.chainrings!.join(' · ') }} }
              @if (draft.cassette?.length) { &nbsp;|&nbsp; Cogs: {{ draft.cassette!.join(' · ') }} }
              @if (draft.wheel_circumference_mm) { &nbsp;|&nbsp; Aro: {{ draft.wheel_circumference_mm }} mm }
            </span>
            <button type="button" class="btn ghost" (click)="editarDentes.set(!editarDentes())">
              {{ editarDentes() ? 'fechar' : 'editar dentes na mão' }}
            </button>
          </label>
          @if (editarDentes()) {
            <label style="grid-column: span 3">
              Dentes das coroas (separados por vírgula)
              <input [ngModel]="coroasTexto()" (ngModelChange)="lerCoroas($event)" placeholder="42, 34, 24" />
            </label>
            <label style="grid-column: span 3">
              Dentes dos cogs (separados por vírgula, do menor pro maior)
              <input [ngModel]="cogsTexto()" (ngModelChange)="lerCogs($event)" placeholder="14, 16, 18, 20, 24, 28, 34" />
            </label>
          }
```

- [ ] **Step 2: Acrescentar o estilo**

No array `styles`, acrescentar:

```css
      .dentes { font-family: var(--mono); font-size: 0.72rem; color: var(--graphite); text-transform: none; letter-spacing: 0; }
```

- [ ] **Step 3: Acrescentar o estado e os métodos**

Na classe `BikesComponent`, acrescentar `DrivetrainPresets` ao import de `../core/models` e:

```typescript
  presets = signal<DrivetrainPresets | null>(null);
  editarDentes = signal(false);
  coroaPreset = signal<string | null>(null);
  catracaPreset = signal<string | null>(null);
  aroPreset = signal<string | null>(null);

  aplicarCoroa(label: string | null): void {
    this.coroaPreset.set(label);
    this.draft.chainrings = this.presets()?.chainrings.find((p) => p.label === label)?.value ?? null;
  }

  aplicarCatraca(label: string | null): void {
    this.catracaPreset.set(label);
    this.draft.cassette = this.presets()?.cassettes.find((p) => p.label === label)?.value ?? null;
  }

  aplicarAro(label: string | null): void {
    this.aroPreset.set(label);
    this.draft.wheel_circumference_mm =
      this.presets()?.wheels.find((p) => p.label === label)?.value ?? null;
  }

  coroasTexto(): string {
    return (this.draft.chainrings ?? []).join(', ');
  }

  cogsTexto(): string {
    return (this.draft.cassette ?? []).join(', ');
  }

  /** Editar na mao desliga o preset: a lista de dentes e a fonte da verdade. */
  lerCoroas(texto: string): void {
    this.draft.chainrings = this.lerNumeros(texto);
    this.coroaPreset.set(null);
  }

  lerCogs(texto: string): void {
    this.draft.cassette = this.lerNumeros(texto);
    this.catracaPreset.set(null);
  }

  private lerNumeros(texto: string): number[] | null {
    const numeros = texto
      .split(',')
      .map((p) => Number(p.trim()))
      .filter((n) => Number.isFinite(n) && n > 0);
    return numeros.length ? numeros : null;
  }
```

No `ngOnInit()`, acrescentar:

```typescript
    this.api.drivetrainPresets().subscribe((data) => this.presets.set(data));
```

E no `create()`, dentro do `subscribe`, trocar a linha de reset do draft por:

```typescript
      this.draft = { kind: 'speed', is_default: false };
      this.coroaPreset.set(null);
      this.catracaPreset.set(null);
      this.aroPreset.set(null);
      this.editarDentes.set(false);
```

- [ ] **Step 4: Mostrar a transmissão no card da bike**

No template, dentro de `<article class="card bike">`, logo depois do `<p class="context">`:

```html
              @if (bike.chainrings?.length && bike.cassette?.length) {
                <p class="dentes" style="margin: 0 0 10px">
                  {{ bike.chainrings!.join('-') }} × {{ bike.cassette![0] }}-{{ bike.cassette![bike.cassette!.length - 1] }}
                  ({{ bike.chainrings!.length * bike.cassette!.length }} marchas)
                </p>
              }
```

- [ ] **Step 5: Botão de editar no card da bike**

Sem isto, contar os dentes da catraca não teria onde ser digitado, e o conserto do PATCH da Task 6 não teria quem o chamasse. No template, trocar o botão "Remover" do card por:

```html
              <div style="display:flex; gap:8px">
                <button class="btn ghost" (click)="editar(bike)">Editar</button>
                <button class="btn ghost" (click)="remove(bike)">Remover</button>
              </div>
```

E trocar o cabeçalho e o botão do formulário de cadastro por:

```html
          <h2>{{ editandoId() ? 'Editar bike' : 'Adicionar bike' }}</h2>
```

```html
        <div style="display:flex; gap:8px">
          <button class="btn" (click)="salvar()" [disabled]="!draft.name">
            {{ editandoId() ? 'Salvar alterações' : 'Salvar bike' }}
          </button>
          @if (editandoId()) {
            <button class="btn ghost" (click)="limparFormulario()">Cancelar</button>
          }
        </div>
```

- [ ] **Step 6: Estado e métodos de edição**

Na classe `BikesComponent`, acrescentar:

```typescript
  editandoId = signal<number | null>(null);

  editar(bike: Bike): void {
    this.editandoId.set(bike.id);
    // Copia, nao referencia: editar o formulario nao deve mexer no card antes de salvar.
    this.draft = { ...bike };
    this.editarDentes.set(false);
    // Reencontra o preset a partir dos dentes, para os selects nao ficarem vazios.
    const p = this.presets();
    this.coroaPreset.set(
      p?.chainrings.find((x) => this.mesmaLista(x.value, bike.chainrings))?.label ?? null,
    );
    this.catracaPreset.set(
      p?.cassettes.find((x) => this.mesmaLista(x.value, bike.cassette))?.label ?? null,
    );
    this.aroPreset.set(
      p?.wheels.find((x) => x.value === bike.wheel_circumference_mm)?.label ?? null,
    );
    window.scrollTo({ top: document.body.scrollHeight / 2, behavior: 'smooth' });
  }

  salvar(): void {
    const id = this.editandoId();
    const done = () => {
      this.message.set(
        id ? 'Bike atualizada.' : 'Bike cadastrada. Agora atribua um treino a ela para ensinar os sensores.',
      );
      this.limparFormulario();
      this.load();
    };
    if (id) {
      this.api.updateBike(id, this.draft).subscribe(done);
    } else {
      this.api.createBike(this.draft).subscribe(done);
    }
  }

  limparFormulario(): void {
    this.editandoId.set(null);
    this.draft = { kind: 'speed', is_default: false };
    this.coroaPreset.set(null);
    this.catracaPreset.set(null);
    this.aroPreset.set(null);
    this.editarDentes.set(false);
  }

  private mesmaLista(a: number[], b: number[] | null | undefined): boolean {
    return !!b && a.length === b.length && a.every((v, i) => v === b[i]);
  }
```

E remover o método `create()` — `salvar()` cobre os dois casos.

- [ ] **Step 7: Verificar na tela**

```bash
cd "d:/AI Solution/Bike_Graph/frontend"
npx tsc --noEmit -p tsconfig.app.json
```

Abrir `http://localhost:4200/bikes` e conferir:

| O que | Esperado |
|---|---|
| Selects de transmissão | Os três aparecem no formulário |
| Escolher "3x MTB 42-34-24" | A linha de resumo mostra `Coroas: 42 · 34 · 24` |
| "editar dentes na mão" | Abre os dois campos de texto, já preenchidos |
| Card da Rockrider | Mostra `42-34-24 × 14-34 (21 marchas)` |
| Botão "Editar" | Preenche o formulário e os selects com os valores da bike |
| Salvar alterações | Marca, modelo, ano e peso **continuam lá** (era o bug do PATCH) |

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/pages/bikes.component.ts
git commit -m "feat(garagem): secao Transmissao com presets, edicao manual de dentes e edicao de bike"
```

---

## Task 11: Gráfico de cobertura no painel de telemetria

**Files:**
- Modify: `frontend/src/app/shared/telemetry-panel.component.ts`

- [ ] **Step 1: Trocar o card de marchas no template**

Substituir o bloco `@if (analysis!.gears?.available) { ... }` inteiro por:

```html
      @if (analysis!.gears?.available) {
        <div class="grid cols-2" style="margin-bottom:20px">
          <div class="card">
            <h2>{{ coverage() ? 'Cobertura de marchas' : 'Marchas usadas' }}</h2>
            <div class="chart-box" [style.height.px]="coverage() ? 420 : 260">
              @if (gearChart(); as cfg) { <app-chart [config]="cfg" /> }
            </div>
          </div>
          <div class="card">
            <h2>Leitura das marchas</h2>
            @if (coverage(); as cov) {
              <div class="grid cols-2" style="gap:12px; margin-bottom:14px">
                <div class="plate">
                  <span class="label">Faixas usadas</span>
                  <span class="value">{{ cov.bands_used }}</span>
                  <span class="unit">de {{ cov.bands_total }}</span>
                </div>
                <div class="plate">
                  <span class="label">Desenvolvimento típico</span>
                  <span class="value">{{ analysis!.gears!.median_development_m | num: 1 }}</span>
                  <span class="unit">m/pedalada</span>
                </div>
              </div>
              <p>{{ cov.insight }}</p>
              <p class="footnote" style="margin-top:12px">
                Relações que dão o mesmo desenvolvimento aparecem juntas — velocidade dividida por
                cadência não tem como dizer em qual coroa você estava. Mas isso só atrapalha saber
                <em>qual</em> você usou: faixa vazia é faixa vazia para todas as relações dela.
              </p>
            } @else {
              <div class="grid cols-2" style="gap:12px; margin-bottom:14px">
                <div class="plate">
                  <span class="label">Desenvolvimento típico</span>
                  <span class="value">{{ analysis!.gears!.median_development_m | num: 1 }}</span>
                  <span class="unit">m/pedalada</span>
                </div>
                <div class="plate">
                  <span class="label">Faixa usada</span>
                  <span class="value">{{ analysis!.gears!.spread_m | num: 1 }}</span><span class="unit">m</span>
                </div>
              </div>
              <p>{{ analysis!.gears!.insight }}</p>
              <p class="footnote" style="margin-top:12px">
                Desenvolvimento é quantos metros a bike anda a cada volta completa do pedal. Sai de
                velocidade dividida por cadência, sem precisar de nenhum sensor a mais. Declare a
                transmissão da bike na Garagem para ver quais relações ficaram paradas.
              </p>
            }
          </div>
        </div>
      }
```

- [ ] **Step 2: Acrescentar os métodos**

Na classe `TelemetryComponent`, acrescentar `GearCoverage` ao import de `../core/models` e:

```typescript
  coverage(): GearCoverage | null {
    return this.analysis?.gears?.coverage ?? null;
  }
```

E substituir `gearChart()` inteiro por:

```typescript
  gearChart(): ChartConfiguration | null {
    const cov = this.coverage();
    return cov ? this.coverageChart(cov) : this.histogramChart();
  }

  /**
   * Uma barra por relacao declarada, em vez de faixas arbitrarias de 0,25 m.
   * Faixa parada nao tem barra para desenhar - o "· parada" no rotulo e que
   * carrega a informacao, porque barra de comprimento zero nao se ve.
   */
  private coverageChart(cov: GearCoverage): ChartConfiguration {
    return {
      type: 'bar',
      data: {
        labels: cov.bands.map((b) => (b.used ? b.label : b.label + ' · parada')),
        datasets: [
          {
            label: 'minutos',
            data: cov.bands.map((b) => Math.round((b.seconds / 60) * 10) / 10),
            backgroundColor: '#0e1f2b',
            borderRadius: 2,
          },
        ],
      },
      options: {
        indexAxis: 'y',
        plugins: { legend: { display: false } },
        scales: {
          x: { title: { display: true, text: 'minutos' } },
          y: { grid: { display: false }, ticks: { font: { size: 10 } } },
        },
      },
    };
  }

  private histogramChart(): ChartConfiguration | null {
    const histogram = this.analysis?.gears?.histogram;
    if (!histogram?.length) {
      return null;
    }
    const peaks = new Set((this.analysis?.gears?.gears_used ?? []).map((g) => g.development_m));
    return {
      type: 'bar',
      data: {
        labels: histogram.map((h) => h.development_m.toFixed(1)),
        datasets: [
          {
            label: 'segundos',
            data: histogram.map((h) => h.seconds),
            backgroundColor: histogram.map((h) => (peaks.has(h.development_m) ? '#d8930b' : 'rgba(14,31,43,0.55)')),
            borderRadius: 1,
          },
        ],
      },
      options: {
        plugins: { legend: { display: false } },
        scales: {
          x: { title: { display: true, text: 'metros por pedalada' }, ticks: { maxTicksLimit: 12 } },
          y: { title: { display: true, text: 'segundos' } },
        },
      },
    };
  }
```

- [ ] **Step 3: Verificar**

```bash
cd "d:/AI Solution/Bike_Graph/frontend"
npx tsc --noEmit -p tsconfig.app.json
```

Abrir `http://localhost:4200/treinos/1`: o card vira "Cobertura de marchas" com 14 barras horizontais, `24x34 · parada` sem barra, e o texto do aviso de 15% fora de relação.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/shared/telemetry-panel.component.ts
git commit -m "feat(telemetria): grafico de cobertura de marchas por relacao declarada"
```

---

## Task 12: Seletor de bike no treino, e verificação fim a fim

**Files:**
- Modify: `frontend/src/app/pages/activity-detail.component.ts`

- [ ] **Step 1: Acrescentar o seletor no template**

No cabeçalho da seção, substituir o bloco `<span class="eyebrow">` por:

```html
            <span class="eyebrow">
              {{ r.started_at | rideDate }} · {{ r.device ?? 'iGPSPORT' }}
            </span>
            <h1>{{ r.title }}</h1>
            <div class="bike-pick">
              <span class="eyebrow">Bike</span>
              <select [ngModel]="r.bike_id ?? 0" (ngModelChange)="trocarBike($event)">
                <option [ngValue]="0">— nenhuma —</option>
                @for (b of bikes(); track b.id) {
                  <option [ngValue]="b.id">{{ b.name }}</option>
                }
              </select>
            </div>
```

- [ ] **Step 2: Acrescentar o estilo**

Acrescentar um array `styles` ao decorador `@Component` (o componente ainda não tem um):

```typescript
  styles: [
    `
      .bike-pick { display: flex; align-items: center; gap: 8px; margin-top: 6px; }
      .bike-pick select {
        font-family: var(--body);
        font-size: 0.9rem;
        color: var(--ink);
        border: 1px solid var(--rule);
        border-radius: var(--radius);
        padding: 5px 8px;
        background: #fff;
      }
    `,
  ],
```

- [ ] **Step 3: Acrescentar estado e método**

Acrescentar `FormsModule` ao `imports` do componente e ao import do Angular:

```typescript
import { FormsModule } from '@angular/forms';
```

E na classe, acrescentar `Bike` ao import de `../core/models` e:

```typescript
  bikes = signal<Bike[]>([]);

  /**
   * Trocar a bike muda a analise, nao so o rotulo: peso, pneu e postura entram
   * na estimativa de potencia, e a transmissao declarada e o que gera a
   * cobertura de marchas. Por isso recarrega a analise junto.
   */
  trocarBike(bikeId: number): void {
    const id = this.ride()?.id;
    if (!id) {
      return;
    }
    this.api.updateActivity(id, { bike_id: bikeId }).subscribe(() => {
      this.api.activity(id).subscribe((data) => this.ride.set(data));
      this.api.analysis(id).subscribe((data) => this.analysis.set(data));
    });
  }
```

No `ngOnInit()`, acrescentar:

```typescript
    this.api.bikes().subscribe((data) => this.bikes.set(data));
```

- [ ] **Step 4: Verificar que compila**

```bash
cd "d:/AI Solution/Bike_Graph/frontend"
npx tsc --noEmit -p tsconfig.app.json
```

- [ ] **Step 5: Rodar a bateria inteira**

```bash
cd "d:/AI Solution/Bike_Graph/backend"
./.venv/Scripts/python.exe -m pytest tests/ -v
```

Esperado: 22 passed.

- [ ] **Step 6: Teste de aceitação do spec §11**

Com backend e frontend no ar, abrir `http://localhost:4200/treinos/1` e conferir:

| O que | Esperado |
|---|---|
| Card de marchas | Título "Cobertura de marchas", 14 barras |
| Faixa parada | `24x34 · parada`, sem barra |
| Placa | "Faixas usadas 13 de 14" |
| Aviso | Texto sobre 15% fora de relação, citando catraca e aro |
| Seletor de bike | Mostra "Rockrider ST100"; trocar para "nenhuma" faz a seção de cobertura sumir e o histograma antigo voltar |

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/pages/activity-detail.component.ts
git commit -m "feat(treino): seletor de bike que recarrega analise e cobertura"
```

---

## Depois de implementar

**Contar os dentes da catraca.** O escalonamento do meio é suposto (§11 do spec). O balde "fora de relação" em 15% está acima do limiar de aviso de 10% e aponta pra isso. Depois de contar, editar a bike na Garagem — agora que o PATCH não apaga mais nada — e conferir se o número cai. Se não cair, o suspeito passa a ser a circunferência do aro (2288 mm é valor de tabela para 29×2.1; um teste de rolagem dá o real).
