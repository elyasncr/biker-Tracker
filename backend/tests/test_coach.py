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


def test_descanso_nunca_e_alarme():
    """R4. Vermelho neste app e FC, e continua sendo so isso."""
    cenarios = [
        coach.readiness(_rides([0, 1, 2, 3]), _pmc({0: 0.0}), HOJE),
        coach.readiness(_rides([1, 4, 8]), _pmc({0: -25.0, 3: -10.0}), HOJE),
        coach.readiness(_rides([0, 1, 2, 3, 4, 5, 6]), _pmc({0: -60.0, 3: -20.0}), HOJE),
    ]
    for r in cenarios:
        assert r["severity"] == "info", r["state"]


COBRANCA = [
    "deveria", "devia", "falhou", "falhar", "perdeu", "fracasso", "preguica",
    "desculpa", "vergonha", "abandonou", "desistiu", "atrasado",
]


def test_ausencia_nao_gera_cobranca():
    """R5. App de habito que envergonha e app desinstalado.

    Tres treinos para passar do MIN_RIDES_TO_READ - com dois, isto caia em
    "sem_historico" e testava a mensagem errada, passando por acidente.
    """
    for dias in (6, 10, 21, 60):
        r = coach.readiness(
            _rides([dias, dias + 5, dias + 10]), _pmc({0: 5.0, 3: 5.0}), HOJE
        )
        assert r["state"] == "convite", f"{dias} dias deveria virar convite, veio {r['state']}"
        texto = (r["headline"] + " " + r["detail"]).lower()
        for palavra in COBRANCA:
            assert palavra not in texto, f"{dias} dias: '{palavra}' em {texto!r}"


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


def test_progresso_agrupa_por_semana_iso():
    """A semana comeca na segunda, igual ao /api/stats/trend que ja existe.

    HOJE e uma segunda-feira, entao um treino hoje e outro ontem (domingo)
    caem em semanas DIFERENTES - e e isso que tem que acontecer.
    """
    p = coach.progress(_rides([0, 1]), [], META, HOJE)
    assert len(p["consistency"]["weeks"]) == 2
