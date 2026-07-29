# SPEC — Bike Tracker

Documento para rodar no Claude Code. Descreve o que já está pronto, as decisões que
sustentam o projeto e o que falta. Leia antes de mexer em qualquer arquivo.

---

## 1. Contexto em três frases

Elyas pedala e exporta os treinos do app iGPSPORT em `.fit`. A iGPSPORT tem uma Open
Platform OAuth2, mas o acesso é aprovado caso a caso por e-mail e o formulário exige razão
social — é canal B2B, inviável para uso pessoal. Por isso o sistema roda sobre os arquivos
`.fit` colocados na pasta `data/`, com o cliente OAuth2 já escrito e desligado por flag.

**Não refaça essa análise.** Se pedirem "usa a API do iGPSPORT", a resposta é: existe, mas
depende de aprovação comercial; o código está em `backend/app/services/igpsport_client.py`
pronto para ligar via `.env`.

---

## 2. Stack e comandos

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0, SQLite, fitdecode, numpy |
| Frontend | Angular 19 standalone, Chart.js 4, Leaflet 1.9 |
| Dados | arquivos `.fit` em `data/`, banco SQLite em `backend/igpsport.db` |

```bash
# backend
cd backend && pip install -r requirements.txt && cp .env.example .env
uvicorn app.main:app --reload          # http://localhost:8000/docs

# frontend
cd frontend && npm install && npm start # http://localhost:4200
```

O backend varre `data/` sozinho no boot. Deduplicação por SHA-256 do arquivo.

---

## 3. Decisões de projeto que devem ser preservadas

Estas não são preferências de estilo — cada uma resolve um problema concreto. Mudar
qualquer uma delas quebra a utilidade do sistema.

### 3.1 A comparação é sempre você contra você, no mesmo dia

O melhor e o pior trecho são medidos contra a mediana **do próprio treino**, não contra um
histórico. Motivo: vento, temperatura, trânsito e sono variam demais entre dias. Comparar
trechos do mesmo pedal isola a variável que interessa — como você estava pedalando naquele
momento.

### 3.2 A métrica de desempenho é potência por batimento, não velocidade

Velocidade mede a estrada (inclinação, vento, piso). Watt por batimento mede o motor. É a
única forma honesta de comparar uma subida de 6% com um trecho plano dentro do mesmo pedal.
Sem potenciômetro, cai para velocidade corrigida pela inclinação dividida pela FC.

### 3.3 Descidas nunca disputam melhor/pior momento

Numa descida a potência despenca e a velocidade dispara — os dois indicadores mentem. Elas
aparecem na lista de trechos, mas ficam fora do ranking. Mesma lógica para trechos com mais
de 30% de tempo sem pedalar.

### 3.4 Explicações só aparecem quando o desvio é grande

Cada regra em `analysis.explain()` tem um limiar mínimo (cadência 8 rpm, potência 12%, FC
4 bpm). Ruído não vira explicação. Um sistema que sempre encontra um motivo mente com
confiança, e aí o usuário para de confiar nas vezes em que ele está certo.

### 3.5 A bike se identifica pelos sensores, não pelo modelo

Sensores ANT+/BLE gravam um número de rádio único no `.fit` e ficam parafusados numa bike
só. O conjunto deles é a impressão digital. O monitor cardíaco é **excluído de propósito**:
a cinta vai com o ciclista, não com a bike — incluí-la faria a mesma bike parecer duas
quando a cinta descarrega.

Fluxo: o usuário nomeia a bike uma vez → `assign_and_learn()` grava a assinatura e adota
todos os treinos órfãos com os mesmos sensores, inclusive os antigos.

### 3.7 A altitude é alisada antes de virar inclinação — em segundos, não em amostras

Barômetro treme. Sem a janela de suavização de **15 segundos** em `detect_segments()`, o
trajeto vira centenas de micro-trechos sem significado. Trechos abaixo de 200 m são
fundidos ao vizinho.

**A janela é medida em segundos de pedal e convertida para amostras pela taxa real de
gravação** (`SMOOTH_WINDOW_S`, `GRADIENT_WINDOW_S`, `_samples_for()`). O ruído do barômetro
acontece numa escala de tempo, não de amostras — e a série quase nunca é 1 Hz: o BSC100S
grava em *smart recording* (um ponto a cada 1 a 8 s) e o `downsample()` ainda reduz tudo a
1200 pontos antes do banco. Com as janelas fixas em amostras, 15 amostras viravam 100+
segundos de estrada, a inclinação era alisada até quase sumir e **o pedal inteiro virava um
único trecho plano — sem dois candidatos, o melhor/pior momento não existia**. Medido num
pedal real gravado a 7 s por amostra: inclinação máxima de 1,98% na versão em amostras,
8,52% na versão em segundos, contra 7,65% gravados pelo próprio aparelho. A 1 Hz as duas
versões dão exatamente o mesmo resultado.

O mesmo vale para `terrain_summary()`, que alimenta Grau+ e VAM+ na tela de resumo.

**Use sempre `_smooth()`, nunca `np.convolve(..., mode="same")`.** O `mode="same"` preenche as
bordas com zero, o que fazia a altitude despencar de 21 m para perto de 0 nos primeiros e
últimos segundos de todo treino — inventando uma rampa que contaminava inclinação, VAM e
potência estimada. Esse bug já custou uma rodada de correção; não o reintroduza.

### 3.8 Razão positiva explica trecho bom; razão negativa explica trecho ruim

`explain()` marca cada regra com `positive` e filtra por `is_best`. Sem isso o sistema chegava
a dizer "seu melhor momento foi porque você ficou 17% sem pedalar" — o que não explica nada e
faz o usuário perder a confiança no resto.

### 3.9 `started_at` guarda a hora local do pedal, não UTC

O `.fit` grava a mesma hora duas vezes na mensagem `activity`: `timestamp` em UTC e
`local_timestamp` no relógio do aparelho. A diferença é o fuso onde o treino aconteceu —
mais confiável que o fuso do servidor, que pode nem ser o mesmo. `fit_parser.utc_offset()`
extrai isso e o horário é gravado já convertido.

Guardar UTC fazia um pedal das 18:22 aparecer como 21:22 na lista, porque o `new Date()` do
JavaScript lê string ISO sem offset como hora local. Pior: **um pedal que começasse depois
das 21h aparecia com a data do dia seguinte**. Quando o arquivo não traz `local_timestamp`,
fica o UTC mesmo — um horário deslocado é melhor que um chute de fuso.

### 3.10 Nenhum tempo é contado em número de amostras

Consequência da 3.7, mas vale isolado porque pega em outros lugares: a série quase nunca é
1 Hz. Qualquer duração calculada como `contagem × 1.0` sai dividida pela taxa real de
gravação. Foi o que acontecia com tempo de barriga, marcha pesada, faixas de cadência e o
histograma de marchas — num pedal gravado a 7 s por amostra a telemetria reportava 14% do
treino e parecia perfeitamente plausível.

`analysis.analyze()` deriva a taxa sozinho da mediana dos intervalos da série `t`
(`effective_sample_rate()`) quando ninguém passa o valor. **Não volte a assumir 1 Hz.**

---

## 4. Mapa do código

```
backend/app/
├── main.py                  FastAPI, CORS, sync no lifespan
├── config.py                .env via pydantic-settings
├── models.py                Activity, ActivityStream, Bike, SyncLog, OAuthToken
├── schemas.py               contratos de resposta
├── routers/
│   ├── activities.py        lista, detalhe, patch, delete
│   ├── analysis.py          /analysis, /route, /similar-segments
│   ├── bikes.py             CRUD, claim, unassigned
│   ├── stats.py             totais, tendência, PMC, curva, zonas, recordes
│   └── sync.py              varredura, upload, endpoints iGPSPORT
└── services/
    ├── fit_parser.py        leitura .fit + impressão digital dos sensores
    ├── metrics.py           NP, IF, TSS, TRIMP, curva de potência, zonas, PMC
    ├── analysis.py          ⭐ motor de telemetria (trechos, melhor/pior, cadência)
    ├── bikes.py             casamento e aprendizado de assinaturas
    ├── ingest.py            varredura da pasta, deduplicação
    └── igpsport_client.py   OAuth2 pronto, desligado por flag

frontend/src/app/
├── core/                    ApiService + tipos espelhando os schemas
├── shared/
│   ├── chart.component.ts   wrapper Chart.js
│   ├── route-map.component.ts    ⭐ mapa Leaflet colorido por métrica
│   ├── telemetry-panel.component.ts  ⭐ painel melhor/pior + cadência
│   └── format.pipe.ts       duração, data, número
└── pages/                   dashboard · treinos · detalhe · garagem
```

---

## 5. Sistema visual (siga, não reinvente)

Referência: papel milimetrado de laboratório + número de peito de prova ciclística.
Tokens em `frontend/src/styles.css`.

- **Paleta:** `--paper` #eef1f4 · `--ink` #0e1f2b · `--graphite` #64798a · `--pulse` #b81d4c
  (FC) · `--watt` #d8930b (potência) · `--climb` #2e7d6b (altimetria)
- **Tipos:** Oswald (números, condensada, como bib de prova) · IBM Plex Sans (texto) ·
  IBM Plex Mono (dados e rótulos)
- **Elemento assinatura:** a "placa" (`.plate`) — número enorme com rótulo pequeno em cima e
  filete colorido no topo indicando a família da métrica
- **Regra:** cor semântica é obrigatória. Vermelho é sempre FC, âmbar é sempre potência,
  verde é sempre altimetria. Nunca use cor decorativa.

---

## 6. Endpoints

| Método | Rota | Retorno |
|---|---|---|
| GET | `/api/activities` | lista (`?bike_id=`, `?start=`, `?end=`) |
| GET | `/api/activities/{id}` | detalhe + séries temporais |
| GET | `/api/activities/{id}/analysis` | ⭐ trechos, melhor/pior + razões, cadência, pacing, parciais |
| GET | `/api/activities/{id}/route` | pontos GPS com métricas para o mapa |
| GET | `/api/activities/{id}/similar-segments` | mesma subida em outros treinos, com delta |
| GET/POST/PATCH/DELETE | `/api/bikes` | garagem |
| POST | `/api/bikes/{id}/claim/{activity_id}` | atribui e aprende a assinatura |
| GET | `/api/bikes/unassigned` | órfãos agrupados por assinatura |
| POST | `/api/sync` | varre `data/` (`?force=true` recalcula tudo) |
| GET | `/api/stats/*` | totals, trend, pmc, power-curve, zones, records, settings |

---

## 7. Backlog — ordem sugerida

### Prioridade alta

1. **Expor W/kg** no dashboard. `RIDER_WEIGHT_KG` e `Bike.weight_kg` já existem e alimentam o
   modelo de potência; falta só dividir e mostrar.
2. **Estimativa automática de FTP.** `power_model.estimate_ftp()` já existe (20 min × 0,95) mas
   não está ligada a nenhuma rota. Ligar na curva de potência e sugerir atualizar o `.env`.
3. **Segmentos nomeados e persistidos.** Hoje `similar-segments` recalcula a análise dos 30
   treinos anteriores a cada chamada — funciona, mas é lento com histórico grande. Criar
   tabela `Segment` com o resultado, indexada por geohash do ponto de partida.
4. **Watcher da pasta `data/`** (watchdog) para importar assim que o arquivo cair, sem
   precisar clicar em sincronizar.

### Prioridade média

5. **Detecção de intervalados.** Achar blocos repetidos de esforço alto e reportar como
   série: "6 × 4 min a 285 W, com queda de 8% do primeiro para o último tiro". Isso responde
   uma pergunta que o gráfico bruto não responde: você aguentou a série inteira?
6. **Comparar dois treinos lado a lado** na mesma rota, com o mapa mostrando onde ganhou e
   perdeu tempo — a versão "ghost lap" da F1.
7. **Metas semanais** de volume/carga com barra de progresso.
8. **Exportar o resumo do pedal** como imagem para compartilhar.

### Prioridade baixa

9. Detecção de vento usando diferença entre potência e velocidade em trechos planos.
10. Alertas de manutenção por bike (`chain_due_in_km` já existe, falta a interface).
11. **Identificar bike pela calibração da roda.** O `.fit` traz distância do sensor de velocidade
    (voltas × circunferência) e, separadamente, posição GPS. Bikes com aros/pneus diferentes
    produzem razões distintas entre as duas. É um sinal real, mas ruidoso por causa do erro de
    GPS — só vale a pena se a atribuição manual incomodar.

---

## 8. Como testar sem ter arquivos `.fit`

`fit-tool` (pip) escreve `.fit` sintético. Gere pedais com relevo, GPS e `device_info` com
`serial_number` diferentes para testar a identificação de bike. Os arquivos precisam ter:

- `record` a 1 Hz com `distance`, `speed`, `altitude`, `position_lat/long`, `heart_rate`,
  `cadence`, `power`
- pelo menos dois `device_info` com `device_index` ≥ 1 e `serial_number` distintos
- uma mensagem `session` com `total_elapsed_time`, `total_distance`, `total_ascent`

Para exercitar as regras de explicação, gere um pedal com decaimento proposital: potência
caindo ~20% e cadência caindo ~15 rpm ao longo do treino faz o motor detectar fadiga e
deriva cardíaca.

---

## 9. Armadilhas conhecidas

- **Angular:** `private route = inject(ActivatedRoute)` colide com qualquer signal chamado
  `route`. O signal do trajeto se chama `routeData` por isso.
- **Leaflet:** é CommonJS. Já está em `allowedCommonJsDependencies` no `angular.json`.
- **Build offline:** `optimization.fonts.inline` está `false` porque o inline exige acesso ao
  Google Fonts em tempo de build.
- **Semicírculos:** `.fit` grava lat/lon em semicírculos. A conversão (`× 180 / 2³¹`) já está
  em `fit_parser.RECORD_FIELDS`.
- **Cadência média** exclui os zeros de propósito (`avg("cadence", skip_zeros=True)`) — é assim
  que o app do iGPSPORT calcula. Incluir os zeros de semáforo derruba o número e não descreve
  o giro do ciclista.
- **`terrain_summary()` recebe duração *elapsed*, não a do cronômetro.** A série de registros
  cobre o pedal inteiro incluindo paradas; usar o tempo em movimento infla VAM e inclinação.
- **`avg_speed` do `.fit`** vem em m/s. Já convertido para km/h no parser — não converta de novo.
