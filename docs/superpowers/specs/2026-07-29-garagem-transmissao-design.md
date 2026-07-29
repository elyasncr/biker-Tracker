# Design — Transmissão declarada e cobertura de marchas

**Data:** 2026-07-29
**Escopo:** Garagem — declarar a transmissão da bike e cruzar com o que foi usado no treino.
**Fora de escopo:** a aba Treinador (vira spec próprio, depois de acumular histórico).

---

## 1. Objetivo

Responder uma pergunta que o ciclocomputador não responde: **quais marchas da minha bike
eu não uso?** Disso sai a decisão prática — esse cassete serve pro terreno que eu pedalo,
ou tem relação morta pendurada aí?

O sistema já infere o *desenvolvimento* (metros que a bike anda por volta de pedal) a partir
de velocidade ÷ cadência, sem sensor extra, em `analysis.gear_report()`. O que falta é o
outro lado da conta: as relações que a bike **tem**. Com as duas metades, a diferença entre
elas é a resposta.

## 2. Descobertas que motivam o design

Duas coisas apuradas em cima de dados reais, não de suposição.

### 2.1 Os `.fit` não trazem os sensores da bike

O arquivo `ride-0-2026-07-27-18-22-09.fit` tem exatamente dois `device_info`, e os dois são
o próprio ciclocomputador (`manufacturer: igpsport`, `product: 103`, mesmo serial). Nenhum
registro de sensor de velocidade ou cadência — apesar da cadência estar gravada em 377 dos
379 pontos.

**Consequência:** a impressão digital de sensores da SPEC §3.5 não distingue bikes deste
usuário. Ela só reconhece o ciclocomputador. A atribuição precisa ser explícita (bike padrão
+ seletor por treino), não inferida.

*Confiança:* verificado em um arquivo. Se um `.fit` futuro trouxer sensores, revisar.

### 2.2 Numa transmissão 3x, quase metade das marchas é duplicata mecânica

Relações diferentes produzem o mesmo desenvolvimento. Na Rockrider ST100 (42-34-24 × 14-34,
aro 2288 mm), `24×24` e `34×34` dão **exatamente** 2,29 m; `42×28` e `24×16` dão exatamente
3,43 m. Das 21 combinações mecânicas, sobram **14 faixas distinguíveis**.

Velocidade ÷ cadência não consegue dizer em qual coroa o ciclista estava. Qualquer relatório
que afirme "você usou a 50×19" numa 2x/3x está chutando.

**Mas a ambiguidade só atinge a atribuição de uso, não a de não-uso.** Se uma faixa ficou
vazia, todas as relações dela ficaram paradas — sem dúvida. *Vazio é inequívoco.* É por isso
que "marchas não usadas" é a leitura que a física permite fazer com precisão, e "qual marcha
você usou" não é.

## 3. Decisões

| # | Decisão | Motivo |
|---|---|---|
| D1 | Relatar por **faixa de desenvolvimento**, não por marcha individual | Único jeito honesto com colisões (§2.2) |
| D2 | Faixas colidentes aparecem agrupadas (`24×24 = 34×34`) | Não afirmar coroa que não dá pra saber. SPEC §3.4 |
| D3 | Limiar de colisão **relativo: 4%** do desenvolvimento | O ruído é multiplicativo, não absoluto (§5.2) |
| D4 | Amostra longe de qualquer relação vai pro balde "fora de relação" | Autoteste do aro e do cassete declarados |
| D5 | Módulo novo `services/drivetrain.py` | `analysis.py` fala do pedal; `drivetrain.py` fala da máquina |
| D6 | Guardar a lista de dentes, não o nome do preset | Duas fontes de verdade divergem; a lista é a verdade |
| D7 | Sem transmissão declarada, a seção não aparece | Mesmo padrão do mapa sem GPS |

## 4. Modelo de dados

Dois campos novos em `Bike`, um já existente:

```python
chainrings: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [42, 34, 24]
cassette:   Mapped[list | None] = mapped_column(JSON, nullable=True)  # [14,16,18,20,24,28,34]
wheel_circumference_mm                                               # JA EXISTE
```

**Validação:** inteiros positivos; coroa entre 20 e 60 dentes; cog entre 9 e 52; aro entre
1000 e 2400 mm. Listas normalizadas (coroas em ordem decrescente, cogs em ordem crescente)
na entrada, para o resto do código não precisar ordenar.

Sem migração automática — o projeto usa `Base.metadata.create_all()`, que **não altera tabela
existente**. Colunas novas em banco já criado precisam de `ALTER TABLE` manual ou de apagar o
`igpsport.db`. Como o banco atual tem 1 treino e é reconstruível por `POST /api/sync`, apagar
é aceitável. Registrar isso no README.

## 5. `services/drivetrain.py`

### 5.1 Interface

```python
PRESETS: dict          # catalogo de coroas, cassetes e aros para a tela
development(cadence: np.ndarray, speed_kmh: np.ndarray) -> np.ndarray
gear_table(chainrings: list[int], cassette: list[int], wheel_mm: int) -> list[Gear]
collapse(gears: list[Gear], tolerance_pct: float) -> list[GearGroup]
coverage(development: np.ndarray, groups: list[GearGroup], sample_rate_s: float) -> dict
```

`development()` vira a casa canônica da fórmula. `analysis.gear_report()` passa a importá-la
daqui em vez de manter cópia própria. `analysis` → `drivetrain` é dependência de mão única;
`drivetrain` não importa nada de `analysis`.

`Gear` = `(development_m, chainring, cog)`. `GearGroup` = lista de `Gear` indistinguíveis,
com desenvolvimento central = média do grupo.

### 5.2 Constantes e sua justificativa

| Constante | Valor | Justificativa |
|---|---|---|
| `COLLISION_PCT` | 0,04 | Cadência é inteira: a 70 rpm, 1 rpm = 1,4% de erro. Velocidade do sensor/GPS ~2-3%. Combinado ~3-4%. Abaixo disso duas marchas são indistinguíveis. |
| `ASSIGN_TOLERANCE_PCT` | 0,05 | Um pouco acima do ruído, para a amostra legítima cair na relação certa; acima disso vai pro balde "fora". |
| `UNUSED_THRESHOLD_S` | 10 | Faixa com menos de 10 s conta como não usada. Uma passagem de troca de marcha não é uso. |
| `OFF_GEAR_WARN` | 0,10 | Acima de 10% do tempo fora de relação, avisar na tela que o cassete ou o aro declarado pode estar errado. |

Medido na ST100: limiar absoluto de 0,20 m dá 12 faixas com grupo máximo de 4; relativo de
4% dá 14 faixas com grupo máximo de 3. O relativo resolve melhor embaixo e não superagrupa
em cima.

**Sensibilidade a registrar.** O resultado de 14 faixas na ST100 está perto de um degrau: o
vão entre `42×18` e `34×14` é de **4,082%**, contra o limiar de 4%. A 4,09% viraria 13
faixas. Isso não é defeito — é a natureza de um limiar — mas quer dizer que o número 14 é
específico desta bike e deste limiar, e não deve ser tratado como constante universal. Quem
mexer em `COLLISION_PCT` precisa saber que 0,04 não tem folga aqui.

### 5.3 Algoritmo de cobertura

1. Filtrar amostras válidas por `cadência ≥ 30 rpm` e `velocidade > 4 km/h` — o mesmo
   critério de entrada do `gear_report()`.

   **Divergência deliberada:** o `gear_report()` aplica ainda um corte extra, descartando
   desenvolvimento fora de 1,5 a 12 m. A cobertura **não** copia esse corte, de propósito.
   Amostra fora de faixa é exatamente o sinal que o balde "fora de relação" existe para
   capturar — descartá-la em silêncio esconderia o aviso de cassete ou aro errado, que é
   metade do valor da leitura. Consequência a aceitar: as duas telas podem contar números de
   amostra ligeiramente diferentes.
2. Para cada amostra, achar o grupo cujo desenvolvimento central está mais próximo.
3. Se `|amostra − centro| ≤ ASSIGN_TOLERANCE_PCT × centro`, contar no grupo; senão, no balde
   "fora de relação". A tolerância é relativa ao **centro do grupo**, não ao valor da amostra
   — assim a largura da faixa é uma propriedade fixa da marcha, e não muda conforme o ruído
   de cada amostra.
4. Converter contagem em segundos multiplicando pela **taxa real de amostragem** — nunca
   assumir 1 Hz (SPEC §3.10).

**Binning por marcha, não por largura fixa.** O histograma existente usa 40 faixas de 0,25 m,
grosso demais: relações colidem a 0,03 m, quinze vezes menos que uma faixa. A cobertura molda
as faixas pelas marchas declaradas.

## 6. Fluxo

`analysis.analyze()` continua sem saber o que é uma bike. A composição é do router:

```
GET /api/activities/{id}/analysis
  ├─ analysis.analyze(stream, ftp)                    -> gears (como hoje)
  └─ se activity.bike tem chainrings e cassette:
       drivetrain.coverage(...)                       -> anexa em gears.coverage
```

Resposta acrescida (só quando há transmissão declarada):

```json
"gears": {
  "available": true,
  "histogram": [...],
  "coverage": {
    "bands": [
      {"development_m": 4.32, "gears": ["34x18"], "seconds": 384, "used": true},
      {"development_m": 1.62, "gears": ["24x34"], "seconds": 0,   "used": false}
    ],
    "off_gear_seconds": 258,
    "off_gear_ratio": 0.14,
    "bands_used": 13,
    "bands_total": 14,
    "insight": "Voce nunca entrou na 24x34, sua relacao mais leve. Num pedal com 61 m de subida isso e esperado - ela existe pra rampa que voce nao encontrou hoje."
  }
}
```

## 7. Interface

### 7.1 Tela do treino

O card "Marchas usadas" já existe em `telemetry-panel.component.ts`. Com transmissão
declarada, **o gráfico troca de eixo**: uma barra por faixa em vez de 40 faixas arbitrárias.
Barra cheia = usada; contorno tracejado = parada.

O histograma de 40 faixas **não fica ao lado — ele é substituído**. Os dois mostram a mesma
grandeza com resoluções diferentes, e manter os dois é ruído. Sem transmissão declarada o
histograma antigo continua sendo o que aparece, exatamente como hoje.

**Cor:** nenhuma nova. Pela SPEC §5, cor é semântica e marcha não é FC, potência nem
altimetria — então `--ink` no usado e contorno `--graphite` no não usado. O "fora de relação"
não vira barra; vira nota de rodapé, virando aviso acima de `OFF_GEAR_WARN`.

**Texto**, na voz do app e só quando há o que dizer: *"Você nunca entrou na 24×34, sua relação
mais leve. Num pedal com 61 m de subida isso é esperado — ela existe pra rampa que você não
encontrou hoje."*

### 7.2 Garagem

Seção **Transmissão** no formulário: coroa (preset), catraca (preset), aro (preset que
preenche o mm), e botão "editar dentes na mão" que expõe os números. O
`wheel_circumference_mm`, que já existe na API, finalmente aparece na tela.

Presets iniciais — cobrir o comum, não o universo:

- **Coroas:** 3x MTB (42-34-24, 44-32-22), 2x speed (50-34, 52-36, 53-39), 1x (32, 34, 38, 40, 42)
- **Catracas:** 7v (14-28, 14-34), 8/9v (11-32, 11-34), 10/11v (11-28, 11-32, 11-34, 11-42), 12v (10-51)
- **Aros:** 700×23c (2096), 700×25c (2105), 700×28c (2136), 700×32c (2155), 29×2.1 (2288), 29×2.25 (2300), 27.5×2.1 (2185), 26×2.1 (2073)

### 7.3 Atribuição

Mínima, porque a bike padrão já cobre o caso de uma bike só:

- `bike_id` aceito no `PATCH /api/activities/{id}` (hoje só título e notas)
- Seletor de bike na tela do treino, ao lado do título
- `ApiService.updateActivity()` no frontend

## 8. Correções obrigatórias incluídas

**`PATCH /api/bikes/{id}` se comporta como PUT.** `bikes.py:71-72` faz `setattr` de todos os
campos do `BikeInput`, e todos têm default `None`. Editar só a catraca apagaria marca,
modelo, ano, peso e aro, e resetaria `kind` para `"speed"`.

Isso deixa de ser defeito latente e vira bloqueio: o fluxo previsto é o usuário cadastrar a
bike, contar os dentes da catraca e voltar pra editar. Ele bate nisso no primeiro uso.

**Correção:** `BikeInput` vira `BikeUpdate` com todos os campos opcionais no PATCH, aplicando
só o que veio (`model_dump(exclude_unset=True)`). O POST continua exigindo `name`.

## 9. Casos de borda

| Situação | Comportamento |
|---|---|
| Bike sem transmissão declarada | `coverage` ausente; seção não desenha |
| Treino sem bike | idem |
| Treino sem cadência | `gear_report` já devolve `available: false` |
| Transmissão 1x | Funciona melhor — zero colisões |
| Aro ou cassete errado | Balde "fora" cresce; aviso acima de 10% |
| Menos de 60 amostras pedalando | `coverage` ausente — amostra pequena demais |
| Coroa ou cassete com um elemento só | Válido (1x); nunca agrupa |

## 10. Testes

O projeto **não tem nenhum teste hoje**. Não é escopo deste trabalho cobrir o que já existe,
mas `drivetrain.py` é o melhor lugar para começar: matemática pura, sem banco, sem I/O, com um
caso real de fixture.

`backend/tests/test_drivetrain.py`, com `pytest` acrescentado ao `requirements.txt`:

- `gear_table()` — 3×7 dá 21 combinações; desenvolvimento de `34×18` com aro 2288 = 4,32 m
- `collapse()` — na ST100, 21 combinações viram 14 faixas; `24×24` e `34×34` caem no mesmo grupo
- `collapse()` com 1x — nunca agrupa
- `coverage()` — faixa sem amostra vem `used: false`
- `coverage()` — amostra fora da tolerância vai pro balde, e o balde entra na razão
- `coverage()` — respeita a taxa de amostragem: o mesmo pedal a 7 s/amostra dá 7× o tempo de 1 s/amostra
- `development()` — 34×18 a 70 rpm com aro 2288 devolve a velocidade coerente (ida e volta)
- Validação — cassete com dente negativo ou zero é rejeitado

## 11. Dados de referência

Bike real do usuário, usada como fixture:

```
Rockrider ST100 2022, aro 29", tamanho L/19'
kind=mtb, weight_kg=15.4 (ficha, tamanho M com pedais), wheel_circumference_mm=2288
chainrings=[42, 34, 24]     Prowheel TA-CQ68
cassette=[14,16,18,20,24,28,34]   Shunfeng 7v 14-34  <- ESCALONAMENTO DO MEIO A CONFIRMAR
```

**Pendência de dado, não de design:** a ficha diz só "14-34, 7 marchas". O escalonamento do
meio é suposto. Evidência de que está errado: no pedal de 27/07, os picos de 4,38 m e 5,38 m
casaram com `34×18` e `42×18` (erro de 6 e 4 cm), mas o pico de 2,12 m ficou a 16 cm da
vizinha mais próxima — e um cog de 26 no lugar do 28 daria 2,11 m. Os dois que casaram usam o
cog de 18, presente em qualquer escalonamento; a discordância está exatamente onde os
fabricantes variam. Contar os dentes resolve.

**Saída do protótipo com as constantes deste spec** (colisão 4%, tolerância 5%, não-usada
abaixo de 10 s), no pedal de 27/07 — serve de teste de aceitação da implementação:

```
  1,62 m  24x34                     0,0 min  <- NAO USADA
  1,96 m  24x28                     0,2 min
  2,29 m  24x24 = 34x34             1,5 min
  2,78 m  24x20 = 34x28 = 42x34     0,5 min
  3,05 m  24x18                     0,5 min
  3,24 m  34x24                     0,5 min
  3,43 m  24x16 = 42x28             1,2 min
  3,94 m  34x20 = 24x14 = 42x24     3,6 min
  4,32 m  34x18                     6,4 min   <- mais usada
  4,83 m  42x20 = 34x16             2,3 min
  5,34 m  42x18                     3,0 min
  5,56 m  34x14                     3,7 min
  6,01 m  42x16                     1,5 min
  6,86 m  42x14                     0,5 min

  fora de relacao: 4,5 min (15%)    bands_used=13  bands_total=14
```

Os 15% fora de relação estão acima do limiar de aviso de 10% — consistente com o
escalonamento suposto da catraca estar errado. Depois de contar os dentes, esse número deve
cair; se não cair, o suspeito passa a ser a circunferência do aro.

## 12. Não incluído de propósito

- **Desambiguar a coroa pelo terreno.** Discutido e recusado: seria palpite vestido de
  certeza, contra a SPEC §3.4. Pode voltar depois, marcado como estimativa.
- **Calibrar potência pela circunferência do aro.** Mexe no modelo de física; assunto próprio.
- **Nomear as marchas como manchete.** A nomeação existe como máquina interna do relatório de
  cobertura, não como etiqueta decorativa no gráfico.
- **Detecção automática de bike por sensores.** Impossível com estes arquivos (§2.1).
