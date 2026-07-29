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


def test_gear_table_ignora_dentes_invalidos():
    # Cog zero estourava ZeroDivisionError; dente negativo passava batido e
    # produzia uma marcha de desenvolvimento negativo.
    assert drivetrain.gear_table([42], [0], ST100_WHEEL_MM) == []
    assert drivetrain.gear_table([42], [-14], ST100_WHEEL_MM) == []
    assert drivetrain.gear_table([0], [18], ST100_WHEEL_MM) == []
    # Dente valido sobrevive ao lado de dente invalido
    gears = drivetrain.gear_table([42], [0, 18], ST100_WHEEL_MM)
    assert [g.name for g in gears] == ["42x18"]


def test_gear_table_ignora_dentes_fora_da_faixa_util():
    # 200 dentes nao e uma coroa, e 3 nao e um cog.
    assert drivetrain.gear_table([200], [18], ST100_WHEEL_MM) == []
    assert drivetrain.gear_table([42], [3], ST100_WHEEL_MM) == []


def test_development_e_a_volta_da_conta():
    # A 70 rpm na 34x18 (4.322 m por pedalada), a bike anda 4.322 * 70 m/min.
    esperado_kmh = 4.322 * 70 * 60 / 1000
    cadence = np.array([70.0])
    speed = np.array([esperado_kmh])
    assert drivetrain.development(cadence, speed)[0] == pytest.approx(4.322, abs=0.01)


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


def test_collapse_lista_vazia():
    assert drivetrain.collapse([]) == []


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


def test_coverage_tolerancia_e_relativa_ao_CENTRO_da_faixa():
    """Fixa a regra que o design exige e que nada testava.

    A faixa mais dura da ST100 (42x14 = 6.864 m) nao tem vizinha acima, entao o
    argmin e inequivoco e da para sondar os dois lados da fronteira sem que outra
    faixa roube a amostra. Com tolerancia de 5% do CENTRO, o limite fica em
    6.864 * 1.05 = 7.207 m. Se alguem trocar para 5% da AMOSTRA, o limite anda -
    e estes dois casos passam a discordar.
    """
    groups = _grupos_st100()
    centro = next(g for g in groups if g.label == "42x14").development_m

    dentro = centro * 1.04   # dentro pelas duas regras? nao: so pela do centro
    fora = centro * 1.08     # fora pela do centro

    cad, spd = _pedal_sintetico([dentro], amostras_por_marcha=100)
    r = drivetrain.coverage(cad, spd, groups, sample_rate_s=1.0)
    assert next(b for b in r["bands"] if b["label"] == "42x14")["seconds"] == 100
    assert r["off_gear_seconds"] == 0

    cad, spd = _pedal_sintetico([fora], amostras_por_marcha=100)
    r = drivetrain.coverage(cad, spd, groups, sample_rate_s=1.0)
    assert next(b for b in r["bands"] if b["label"] == "42x14")["seconds"] == 0
    assert r["off_gear_seconds"] == 100


def test_coverage_fronteira_da_tolerancia_e_inclusiva(monkeypatch):
    """Amostra exatamente na borda conta como uso. Mata a mutacao <= para <.

    Construida com ASSIGN_TOLERANCE_PCT=0.5 (via monkeypatch, so para este
    teste) porque e a unica forma de fazer "centro + centro*pct - centro"
    bater bit a bit com a tolerancia recalculada dentro do coverage(). Com o
    valor real (0.05), que nao e fracao binaria exata, a soma-e-subtracao em
    ponto flutuante nunca fecha limpa (erra por ~1 ULP) - um teste que tentasse
    construir a borda com 0.05 falharia no codigo CORRETO, por ruido de
    arredondamento, nao por bug. O que importa aqui e exercitar o operador <=
    em cima de uma igualdade que realmente acontece; ele nao depende da
    magnitude da constante.
    """
    grupo = drivetrain.GearGroup(1.0, (drivetrain.Gear(1.0, 40, 40),))
    monkeypatch.setattr(drivetrain, "ASSIGN_TOLERANCE_PCT", 0.5)
    centro = grupo.development_m
    na_borda = centro + centro * drivetrain.ASSIGN_TOLERANCE_PCT  # 1.5, exato

    cad, spd = _pedal_sintetico([na_borda], amostras_por_marcha=100)
    r = drivetrain.coverage(cad, spd, [grupo], sample_rate_s=1.0)
    assert next(b for b in r["bands"] if b["label"] == "40x40")["seconds"] == 100


def test_coverage_tolerancia_tem_a_largura_declarada():
    """Fixa ASSIGN_TOLERANCE_PCT, que nenhuma mutacao conseguia derrubar.

    A 4% do centro a amostra entra; a 6% ela sai. So passa se a tolerancia
    estiver entre 4% e 6% - qualquer 0.001, 0.01 ou 0.15 quebra.
    """
    groups = _grupos_st100()
    centro = next(g for g in groups if g.label == "42x14").development_m

    cad, spd = _pedal_sintetico([centro * 1.04], amostras_por_marcha=100)
    assert drivetrain.coverage(cad, spd, groups, sample_rate_s=1.0)["off_gear_seconds"] == 0

    cad, spd = _pedal_sintetico([centro * 1.06], amostras_por_marcha=100)
    assert drivetrain.coverage(cad, spd, groups, sample_rate_s=1.0)["off_gear_seconds"] == 100


def test_coverage_off_gear_tambem_respeita_a_taxa():
    """O teste de taxa so olhava as bandas: dava para ignorar a taxa no balde fora."""
    groups = _grupos_st100()
    cad, spd = _pedal_sintetico([8.0], amostras_por_marcha=100)  # nao existe nesta bike
    um_hz = drivetrain.coverage(cad, spd, groups, sample_rate_s=1.0)
    sete_s = drivetrain.coverage(cad, spd, groups, sample_rate_s=7.0)
    assert um_hz["off_gear_seconds"] == 100
    assert sete_s["off_gear_seconds"] == 700


def test_coverage_limiar_de_nao_usada_e_o_declarado():
    """Fixa UNUSED_THRESHOLD_S = 10 s, e que a comparacao e inclusiva (>=).

    100 amostras a 0.1 s dao exatamente 10 s: e usada, na borda. A 0.09 s dao
    9 s: nao e usada. Mutacao para 1 ou 99 quebra os dois lados.
    """
    groups = _grupos_st100()
    centro = next(g for g in groups if g.label == "34x18").development_m
    cad, spd = _pedal_sintetico([centro], amostras_por_marcha=100)

    exatamente_10s = drivetrain.coverage(cad, spd, groups, sample_rate_s=0.1)
    assert next(b for b in exatamente_10s["bands"] if b["label"] == "34x18")["used"] is True

    nove_segundos = drivetrain.coverage(cad, spd, groups, sample_rate_s=0.09)
    assert next(b for b in nove_segundos["bands"] if b["label"] == "34x18")["used"] is False


def test_collapse_encadeia_pelo_ultimo_da_faixa():
    """Tres marchas, cada uma 3% acima da anterior, viram UMA faixa.

    A primeira e a ultima estao a 6% de distancia - mais que o limiar de 4%.
    So agrupam se a comparacao for contra a ULTIMA marcha ja na faixa, e nao
    contra a primeira nem contra o centro. A ST100 nao distingue essas tres
    regras, entao sem este teste a decisao ficava sem cobertura nenhuma.
    """
    escada = [
        drivetrain.Gear(1.000, 40, 40),
        drivetrain.Gear(1.030, 41, 40),
        drivetrain.Gear(1.060, 42, 40),
    ]
    groups = drivetrain.collapse(escada, tolerance_pct=0.04)
    assert len(groups) == 1
    assert len(groups[0].gears) == 3


def test_collapse_centro_e_a_media_e_nao_a_primeira():
    """Substitui o teste tautologico anterior.

    O antigo recalculava a media a partir do proprio grupo e comparava consigo
    mesma - nao tinha como falhar. Aqui o valor esperado e independente: numa
    escada 1.000/1.030/1.060 o centro tem que ser 1.030, nao 1.000.
    """
    escada = [
        drivetrain.Gear(1.000, 40, 40),
        drivetrain.Gear(1.030, 41, 40),
        drivetrain.Gear(1.060, 42, 40),
    ]
    groups = drivetrain.collapse(escada, tolerance_pct=0.04)
    assert groups[0].development_m == pytest.approx(1.030, abs=0.0001)
