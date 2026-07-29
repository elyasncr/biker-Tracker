# Design — Aba Treinador

**Data:** 2026-07-29
**Escopo:** Uma aba que lê o histórico e responde três perguntas: pedalo hoje, o que faço, estou evoluindo.
**Depende de:** nada. O PMC, o modelo de potência e a garagem já existem.

---

## 1. Objetivo do ciclista, e por que ele manda no design

Palavras do usuário: *"pretendo perder peso e melhorar meu condicionamento físico, sem forçar
nada. Apenas mantendo a constância."*

Três consequências que não são estilo, são arquitetura:

1. **A fisiologia certa aqui é volume em Z2 e frequência**, não intensidade. Perda de peso e
   base aeróbica respondem a tempo na sela.
2. **O risco a proteger é parar, não estafar.** Um treinador que empurra demais na terceira
   semana é o que faz o ciclista abandonar. A proteção contra overtraining é secundária.
3. **"Sem forçar" precisa virar invariante testável** (§5), senão vira tom de voz que a
   próxima alteração derruba sem ninguém perceber.

O usuário escolheu três faces (das quatro oferecidas): prontidão, prescrição e progresso.
Ficou de fora "estou treinando demais", parcialmente coberto pela prontidão.

## 2. A decisão central: a moeda não é TSS

**Problema.** O FTP do sistema é `220 W` — o default do `.env`, um chute. Ele alimenta IF,
TSS, CTL, ATL e TSB, ou seja, tudo que um treinador clássico usaria. Medido no pedal real de
27/07 (NP 149,9 W, 36,6 min):

| FTP suposto | IF | TSS | O que um treinador diria |
|---|---|---|---|
| **220** (default, chute) | 0,68 | 28,4 | pedal leve, pode treinar amanhã |
| 190 | 0,79 | 38,0 | moderado |
| 170 | 0,88 | 47,5 | forte, merece recuperação |
| 150 | 1,00 | 61,0 | muito forte, descanso obrigatório |

O mesmo pedal vira "leve" ou "descanso obrigatório" conforme um número que ninguém mediu.

**Decisão.** A moeda do Treinador é **tempo e frequência**, não TSS. Sessenta minutos são
sessenta minutos independente do FTP. Para este objetivo isso não é consolo — é a métrica
fisiologicamente correta.

O TSB entra em **um** lugar: o sinal de descanso, onde o que importa é o sinal e a tendência,
não o valor absoluto. "Você pedalou quatro dias seguidos e a curva está caindo" continua
verdade com o FTP errado.

**Recusado: estimar o FTP automaticamente.** `power_model.estimate_ftp()` existe e não tem
chamador. Ligá-lo seria erro sobre erro — FTP estimado a partir de potência estimada — e a
estimativa passiva subestima sistematicamente, porque em pedal normal ninguém vai all-out.
FTP baixo demais infla IF, infla TSS, infla CTL, e o treinador manda descansar quem está
inteiro. A alternativa, um teste de 20 min no talo, é exatamente o "forçar" descartado.

CTL continua sendo exibida, rotulada como o que é: estimativa apoiada em estimativa.

## 3. Modelo de dados

```python
class WeightEntry(Base):
    __tablename__ = "weight_entries"
    id: int
    measured_on: date          # UNIQUE - um por dia; relancar sobrescreve
    weight_kg: float
    note: str | None

class CoachGoal(Base):
    __tablename__ = "coach_goals"
    id: int                    # linha unica, get-or-create com id=1
    rides_per_week: int        # default 3
    minutes_per_week: int      # default 180
    target_weight_kg: float | None
    updated_at: datetime
```

`measured_on` único evita três pesagens do mesmo dia brigando pela linha de tendência.
Validação: peso entre 30 e 250 kg; data não pode ser futura.

**Colunas novas em banco existente** exigem `ALTER TABLE` — o `create_all()` cria tabela que
falta mas não altera tabela pronta. Aqui são tabelas NOVAS, então `create_all()` resolve
sozinho. Sem migração manual.

### 3.1 O peso corrige a potência estimada

Hoje `ingest.import_file()` usa `settings.rider_weight_kg` fixo. Quem emagrecer 8 kg segue
tendo a potência calculada com o corpo antigo, e a comparação entre meses fica contaminada.

Passa a usar o `WeightEntry` mais próximo da data do treino, caindo para o `.env` quando não
houver nenhum. Consequência a aceitar: `POST /api/sync?force=true` depois de lançar pesos
antigos muda números já vistos. É a correção certa, mas precisa estar documentada.

## 4. Módulo novo: `services/coach.py`

Mesma fronteira do `drivetrain.py`: entra dado, sai leitura. Sem banco, sem HTTP, sem
`Session`. O router monta os insumos e compõe.

```python
def readiness(rides: list[dict], pmc: list[dict], hoje: date) -> dict
def prescription(readiness: dict, goal: dict, semana: dict) -> dict
def progress(rides: list[dict], pesos: list[dict], goal: dict) -> dict
```

`rides` e `pesos` são listas de dicionários simples (data, duração, carga, peso), não objetos
ORM — é o que mantém o módulo testável sem banco.

## 5. As cinco regras do "sem forçar" — invariantes, não tom de voz

**Quem mexe na meta.** A meta é declarada pelo usuário (§3) e só ele a altera. O Treinador
pode **sugerir** uma meta maior — e é essa sugestão que R2 e R3 restringem. A sugestão
aparece como convite com um botão de aceitar; ignorá-la não tem consequência nenhuma, e ela
não reaparece na semana seguinte se for ignorada duas vezes. Sem isso, R2 e R3 não teriam o
que governar.

| # | Regra | Por quê |
|---|---|---|
| R1 | Nunca prescreve acima de Z2 | O vocabulário é duração + "ritmo de conversa". Sem tiro, sem limiar, nem como opção avançada. |
| R2 | Meta sugerida limitada a +10% da média de minutos das últimas 4 semanas | Regra clássica de rampa segura. Restringe a **sugestão de meta**, não a duração de uma sessão isolada. |
| R3 | Nunca sugere meta maior depois de semana abaixo da meta atual | Não bateu = meta alta ou vida atravessou. Subir aí é surdez. |
| R4 | Descanso é sugestão, nunca alarme | Vermelho no app é FC, e continua sendo só isso |
| R5 | Ausência gera convite, não cobrança | App de hábito que envergonha é app desinstalado |

Cada uma vira um teste (§8). Violá-las quebra o build.

## 6. As três leituras

### 6.1 Prontidão — "devo pedalar hoje?"

Avaliada nesta ordem; a primeira que casar vence:

| Condição | Leitura |
|---|---|
| Menos de 3 treinos no histórico | **"Ainda não tenho histórico pra ler"**, com o que falta |
| 4 ou mais dias de calendário consecutivos com treino, terminando ontem ou hoje | Vale uma folga hoje |
| TSB < −20 **e** caindo (TSB de hoje menor que o de 3 dias atrás) | A carga subiu rápido; hoje leve |
| Nada disso | Dia livre |

A primeira linha não é estado de erro — é a tela que o usuário vê nesta semana, e a razão de
o Treinador ser confiável depois. Um treinador que admite não saber é o único em que dá para
acreditar quando diz que sabe.

Poucas regras de propósito, pelo mesmo princípio do §3.4 da SPEC principal: só fala quando o
desvio é grande.

### 6.2 Prescrição — "o que faço hoje?"

- Prontidão pedindo folga → prescrição é folga. Não negocia.
- Semana já batida em pedais **e** em minutos → "meta da semana batida", e qualquer pedal a
  mais é bônus: sugere a duração típica das últimas 4 semanas, sem cobrança
- Senão: `duração = (meta_minutos − minutos já feitos) ÷ max(1, pedais restantes)`.
  O `max(1, …)` cobre o caso de já ter batido a contagem de pedais mas não a de minutos —
  sem ele a conta divide por zero.
- Zona: sempre Z2, descrita como "ritmo de conversa" — dá para falar frases inteiras
- Teto: nunca mais que 1,5× o pedal mais longo das últimas 4 semanas
- Piso: 20 min. Abaixo disso não vale sugerir.
- A semana começa na segunda-feira (ISO), igual ao agrupamento do `/api/stats/trend`

### 6.3 Progresso — "estou evoluindo?"

Quatro linhas, **nesta ordem**, que reflete o objetivo e não a sofisticação da métrica:

1. **Constância** — pedais por semana contra a meta, últimas 8 semanas
2. **Peso** — tendência e variação total desde o primeiro lançamento
3. **Volume** — horas por semana
4. **Condicionamento** — CTL, rotulada como dependente de FTP estimado

O peso registrado **destrava** o W/kg — item 1 do backlog da SPEC principal, parado desde o
início por falta exatamente deste dado. Mas ele **não entra nesta aba**, e a razão é
coerência: W/kg é métrica de potência, e o §2 decidiu que este treinador não fala em
potência porque o FTP é um chute. Exibir W/kg em destaque aqui contradiria a decisão central
e reintroduziria pela porta dos fundos a incerteza que a moeda tempo/frequência existe para
evitar. O lugar dele é o dashboard, junto das outras métricas de potência, num trabalho
próprio.

## 7. API e tela

```
GET  /api/coach                  as tres leituras num payload
GET  /api/coach/goal
PUT  /api/coach/goal
GET  /api/weight                 serie completa
POST /api/weight                 upsert por data
DELETE /api/weight/{data}
```

Peso fica fora do namespace `/coach` de propósito: é dado do atleta, alimenta o modelo de
potência e sobrevive à feature.

**Tela:** rota `/treinador`, item de menu após "Evolução". Prontidão como placa grande no
topo, prescrição abaixo, progresso em quatro blocos. Meta e peso editáveis na própria aba.
Sem cor nova — prontidão e peso não são FC, potência nem altimetria, então tinta (`--ink`),
seguindo o §5 da SPEC principal.

## 8. Testes

`backend/tests/test_coach.py`, mesmo padrão do `test_drivetrain.py` (lógica pura, sem banco).

Cinco testes para as cinco regras:

- `test_nunca_prescreve_acima_de_z2` — varre cenários variados; nenhuma saída menciona
  limiar/tiro/intervalado, e a zona é sempre Z2
- `test_nunca_sobe_mais_que_10_por_cento` — com média de 4 semanas em 200 min, a sugestão
  nunca passa de 220
- `test_nunca_sobe_depois_de_semana_abaixo` — semana abaixo da meta, sugestão não aumenta
- `test_descanso_nunca_e_alarme` — a leitura de descanso não vem com severidade de alerta
- `test_ausencia_nao_gera_cobranca` — 10 dias sem pedalar produz convite, sem palavra de
  cobrança (lista negra explícita de termos)

Mais: a tabela de prontidão caso a caso, a matemática da duração prescrita (teto de 1,5×,
piso de 20 min), o estado de histórico raso, e progresso com peso vazio.

## 9. Casos de borda

| Situação | Comportamento |
|---|---|
| Nenhum treino | Prontidão em "sem histórico"; progresso vazio, sem erro |
| Nenhum peso lançado | Linha de peso ausente; W/kg não aparece |
| Nenhuma meta definida | Default 3 pedais / 180 min, marcado como default |
| Peso com data futura | Rejeitado (422) |
| Treino sem TSS | Entra em constância e volume; fora da CTL |
| Meta zerada pelo usuário | Rejeitada — mínimo 1 pedal / 30 min |

## 10. Fora de escopo, de propósito

- **Periodização.** Não há prova alvo.
- **Detecção de intervalados** (item 5 do backlog). É sobre intensidade, que a R1 proíbe.
- **FTP automático** (item 2 do backlog). É a abordagem recusada no §2.
- **Notificações e lembretes.** Nada que persiga o usuário fora do app.
- **Metas de peso agressivas.** `target_weight_kg` é opcional e serve de referência na
  linha de tendência; o sistema não prescreve déficit calórico nem opina sobre dieta.
