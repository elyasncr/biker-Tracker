# Bike Tracker — evolução dos treinos a partir do iGPSPORT

Backend em **Python (FastAPI)** + frontend em **Angular**, para acompanhar a evolução dos pedais
usando os arquivos `.fit` exportados do app iGPSPORT.

---

## Primeiro: a API do iGPSPORT existe?

**Existe, mas não serve para projeto pessoal.**

A iGPSPORT mantém uma *Open Platform* com OAuth 2.0, documentada em
<https://www.igpsport.com/support/app/openapi>. O problema é o modelo de acesso: não há console
de desenvolvedor onde você cria um app e pega client_id/client_secret na hora. O acesso é
liberado caso a caso, por e-mail (`global@igpsport.com`), e o formulário de solicitação pede:

| Campo | O que pedem |
|---|---|
| Nome do app | até 50 palavras |
| Logo | PNG 120x120, anexo |
| Descrição | até 100 palavras |
| `redirect_url` | endereço de retorno da autorização |
| `callback_url` | webhook para dados de treino |
| **Razão social** | nome da pessoa jurídica |
| Site oficial | link |

Ou seja: é um canal B2B para parceiros (Strava, Intervals.icu e afins). Pedir razão social e logo
já mostra que a porta não é para uso individual. E como as URLs de `authorize`/`token`/atividades
não são publicadas, ninguém consegue nem tentar sem passar pela aprovação.

**Então o projeto foi montado sobre os arquivos `.fit`** — que é o caminho que funciona hoje,
sem depender de aprovação de ninguém. Só que a arquitetura já está preparada para o outro
cenário: existe um `services/igpsport_client.py` completo (authorize, token, refresh, listagem,
download do .fit) desligado por uma flag no `.env`. Se um dia você conseguir as credenciais,
preenche as variáveis, liga `IGPSPORT_ENABLED=true` e o resto do sistema não muda em nada —
a API vira só mais uma fonte que joga `.fit` na mesma pasta `data/`.

Vale registrar um efeito colateral bom dessa escolha: `.fit` é padrão ANT+/Garmin. Se você
trocar de ciclocomputador amanhã (Garmin, Wahoo, Bryton), o projeto continua funcionando.

---

## Como rodar

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # ajuste seu FTP e FC máxima aqui
uvicorn app.main:app --reload
```

Sobe em <http://localhost:8000>. Documentação interativa em <http://localhost:8000/docs>.
Na inicialização ele já varre a pasta `data/` sozinho.

### Frontend

```bash
cd frontend
npm install
npm start
```

Abre em <http://localhost:4200> (o proxy já manda `/api` para a porta 8000).

### Ou tudo de uma vez

```bash
docker compose up --build
```

### Colocando os treinos

Exporte os pedais no app iGPSPORT em `.fit` e jogue os arquivos em `data/` — pode ser em
subpastas, ele varre recursivo. Depois clique em **"Ler pasta data/"** no topo da tela, ou chame
`POST /api/sync`. Dá também para arrastar um `.fit` direto pela tela de Treinos.

Reimportar o mesmo arquivo não duplica nada: cada treino é identificado pelo SHA-256 do arquivo.

---

## Ajuste isto antes de olhar os números

No `.env`:

```
RIDER_WEIGHT_KG=75   # seu peso com roupa e mochila — o mais importante
FTP_WATTS=220        # sua potência de limiar
HR_MAX=190           # sua FC máxima (só se você usar cinta)
HR_REST=55           # sua FC de repouso
```

**O peso é o campo que mais importa no seu caso.** Sem potenciômetro, a potência é calculada
pela física, e a massa entra direto na conta.

FTP e FC máxima entram no cálculo de IF, TSS, zonas e no gráfico de forma. Com os valores
errados, todo o resto fica deslocado. Se você não tem potenciômetro, o sistema usa TRIMP
(carga por frequência cardíaca) no lugar do TSS automaticamente — nesse caso o que importa
acertar é `HR_MAX` e `HR_REST`.

Se mudar o FTP depois, rode `POST /api/sync?force=true` para recalcular tudo.

**Sobre colunas novas no banco:** o SQLAlchemy cria tabela que falta, mas não altera tabela
existente. Se você atualizar o código e aparecer erro de coluna inexistente, ou apague
`backend/igpsport.db` e suba de novo (o banco é reconstruído varrendo `data/`), ou rode um
`ALTER TABLE` para acrescentar só a coluna nova, preservando o que já está lá.

**Peso e potência estimada:** se você lançar pesos antigos na aba Treinador e rodar
`POST /api/sync?force=true`, os números de potência dos treinos antigos mudam — passam a ser
calculados com o peso que você tinha naquela data, não com o valor fixo do `.env`. É a
correção certa, mas não se assuste com os valores diferentes.

---

## Sem potenciômetro e sem cinta: como o sistema ainda mede carga

Se o seu `.fit` traz só velocidade, cadência, GPS e barômetro — que é o caso de quem usa um
BSC100S com sensores de velocidade e cadência —, então TSS, IF e TRIMP seriam todos nulos, e o
gráfico de condicionamento nunca sairia do zero. TSS precisa de watt; TRIMP precisa de batimento.

A saída é calcular a potência pela física. Para manter a bike andando você vence três forças —
atrito do pneu, gravidade na subida e arrasto do ar — mais a inércia quando acelera. Todas são
calculáveis a partir de velocidade, inclinação e massa, que é exatamente o que o aparelho grava.

Isso destrava TSS, curva de potência, zonas e o gráfico de forma inteiro.

**Sobre a precisão, sem enfeitar:** a estimativa erra tipicamente de 10 a 15% contra um
potenciômetro real, e erra mais com vento forte, porque o modelo assume ar parado. Mas erra de
forma *consistente*, e consistência é o que importa para acompanhar evolução — se todo mês o
número sai da mesma conta, a comparação entre os meses continua valendo. O que você não pode
fazer é comparar esse número com o potenciômetro de outra pessoa.

Todo treino com potência calculada aparece marcado como **estimada** na interface. Preencher
peso e tipo da bike na Garagem melhora a conta: uma MTB de 13 kg com pneu cravado gasta bem
mais watt que uma speed de 8 kg na mesma velocidade.

---

## Marchas, a partir de velocidade e cadência

Velocidade dividida por cadência dá o **desenvolvimento**: quantos metros a bike anda a cada
volta completa do pedal. Cada combinação de coroa e cassete tem o seu, então os picos dessa
distribuição são as marchas que você realmente usa — sem precisar de nenhum sensor a mais.

Isso responde uma pergunta que o ciclocomputador não responde: você está trocando marcha
acompanhando o terreno, ou anda o pedal inteiro em duas ou três relações e compensa com a perna?

---

## O que o sistema calcula

| Métrica | Para que serve |
|---|---|
| NP (potência normalizada) | custo fisiológico real do pedal, não a média simples |
| IF (fator de intensidade) | NP ÷ FTP — quão duro foi em relação ao seu limiar |
| TSS | carga do treino; 100 = uma hora no limiar |
| TRIMP | carga por FC, quando não há potenciômetro |
| VI (índice de variabilidade) | NP ÷ média — perto de 1.0 é pedal constante, alto é ritmo picado |
| CTL / ATL / TSB | base, fadiga e frescor ao longo do tempo |
| Curva de potência | melhor esforço médio para 1s até 1h, com data e treino de origem |
| Tempo por zona | onde o treino realmente aconteceu |

**Sobre o TSB:** positivo é descansado, negativo é acumulando fadiga. Ficar muito negativo por
semanas seguidas é o padrão que costuma preceder overtraining — vale usar como sinal de
quando pegar leve, não como meta a bater.

---

## Endpoints

| Método | Rota | O que faz |
|---|---|---|
| GET | `/api/activities` | lista treinos (filtro por `start`/`end`) |
| GET | `/api/activities/{id}` | detalhe + série temporal completa |
| GET | `/api/activities/{id}/analysis` | telemetria: melhor/pior trecho com motivos, cadência, parciais |
| GET | `/api/activities/{id}/route` | pontos GPS com métricas, para o mapa |
| GET | `/api/activities/{id}/similar-segments` | a mesma subida em outros treinos, com o delta |
| GET | `/api/bikes` | garagem, com odômetro por bike |
| POST | `/api/bikes/{id}/claim/{activity_id}` | atribui a bike e aprende os sensores |
| GET | `/api/bikes/unassigned` | treinos sem bike, agrupados por assinatura |
| PATCH | `/api/activities/{id}` | renomeia / anota |
| DELETE | `/api/activities/{id}` | remove do banco (não apaga o `.fit`) |
| POST | `/api/sync` | varre `data/` e importa os novos (`?force=true` recalcula tudo) |
| POST | `/api/upload` | envia um `.fit` pela interface |
| GET | `/api/stats/totals` | totais da janela (`?days=`) |
| GET | `/api/stats/trend` | volume por semana ou mês |
| GET | `/api/stats/pmc` | CTL / ATL / TSB dia a dia |
| GET | `/api/stats/power-curve` | melhores esforços por duração |
| GET | `/api/stats/zones` | tempo por zona de potência e FC |
| GET | `/api/stats/records` | recordes pessoais |
| GET | `/api/igpsport/status` | mostra se a integração está ligada |
| POST | `/api/igpsport/sync` | baixa da API (503 enquanto desligado) |

---

## Estrutura

```
igpsport-tracker/
├── data/                       ← seus .fit vão aqui
├── backend/
│   └── app/
│       ├── main.py             FastAPI + sync na inicialização
│       ├── models.py           Activity, ActivityStream, SyncLog, OAuthToken
│       ├── routers/            activities · stats · sync
│       └── services/
│           ├── fit_parser.py   leitura do .fit (fitdecode)
│           ├── metrics.py      NP, IF, TSS, TRIMP, curva, zonas, PMC
│           ├── ingest.py       varredura da pasta + deduplicação
│           └── igpsport_client.py   OAuth2, pronto e desligado
└── frontend/
    └── src/app/
        ├── core/               ApiService + tipos
        ├── shared/             Chart.js, mapa Leaflet, painel de telemetria, pipes
        └── pages/              dashboard · treinos · detalhe · garagem
```

O banco é SQLite (`backend/igpsport.db`), criado sozinho. Para trocar por Postgres, é só mudar
`DATABASE_URL` no `.env` — o SQLAlchemy cuida do resto.

---

## Telemetria estilo F1

Cada pedal é cortado em trechos pelo relevo (subida, plano, descida) e cada trecho recebe uma
nota. A nota é **potência por batimento** — porque velocidade mede a estrada, e watt por
batimento mede o motor. É o que permite comparar uma subida de 6% com um plano dentro do
mesmo treino. Sem potenciômetro, entra velocidade corrigida pela inclinação dividida pela FC.

O melhor e o pior trecho vêm com o motivo, tipo:

> **Pior momento — km 34,4 a 42,5** (plano, −1,9%) · **−35%**
> • *potência* — Potência 31% abaixo da média (139 W contra 201 W).
> • *fadiga* — Aconteceu nos últimos 30% do pedal, quando sua eficiência já tinha caído 30%
>   em relação ao início. Boa parte disso é cansaço acumulado, não o trecho em si.

Três decisões que sustentam isso:

- **Comparação é sempre você contra você, no mesmo dia.** Mesmo vento, mesma perna, mesma
  estrada. Comparar com o histórico misturaria variáveis demais.
- **Descidas não disputam.** Nelas a potência despenca e a velocidade dispara — os dois
  indicadores mentem. Aparecem na lista, ficam fora do ranking.
- **Só fala quando o desvio é grande.** Cada regra tem limiar mínimo (cadência 8 rpm,
  potência 12%, FC 4 bpm). Um sistema que sempre acha um motivo mente com confiança.

Junto vem: análise de cadência (faixas de giro, torque, tempo de barriga, marcha pesada),
gestão de esforço por quarto do pedal, parciais por quilômetro e comparação das suas subidas
com as tentativas anteriores na mesma ladeira.

---

## Mapa do trajeto

Leaflet com tiles do OpenStreetMap — sem chave de API, sem cadastro. O traçado é colorido
pela métrica que você escolher (velocidade, potência, FC, cadência, altitude), o que
transforma a linha num gráfico sobre o mapa. Os trechos de melhor e pior momento ficam
marcados em cima da rota.

Treino de rolo ou arquivo sem GPS simplesmente não mostra o mapa, com um aviso explicando.

---

## Garagem: qual bike você usou

Cada sensor grava um número de rádio único dentro do `.fit`. **Se** os sensores moram numa bike
só, esse conjunto identifica a bike: você nomeia uma vez e os treinos antigos ganham dono junto.

**Se você move os mesmos sensores entre bikes**, a assinatura identifica os sensores, não a
bike — e confiar nela seria pior que não ter nada, porque carimbaria a bike errada com confiança
total. O sistema percebe isso sozinho: no momento em que a mesma assinatura for reivindicada por
duas bikes diferentes, ele desliga o palpite automático para elas e passa a pedir atribuição
manual. Errar em silêncio seria pior do que perguntar.

Para esse caso existe a **atribuição por período**: você escolhe as datas e a bike, e resolve
vários pedais de uma vez. Quando os sensores viajam, sua memória é o dado mais confiável — e ela
funciona por período ("de maio até julho andei na gravel"), não pedal por pedal.

O monitor cardíaco fica de fora da assinatura de propósito: a cinta vai com você, não com a bike.

Além do odômetro por bike (útil para saber quando trocar corrente), o cadastro alimenta o modelo
de potência: peso, tipo de pneu e postura mudam a física.

---

## Ideias para depois

Veja `SPEC.md` para o backlog completo e priorizado. Os próximos da fila:

- Peso do ciclista no `.env` para habilitar W/kg, a moeda real de subida
- Estimativa automática de FTP pelo melhor esforço de 20 min (× 0,95)
- Detecção de intervalados: "6 × 4 min a 285 W, com queda de 8% do primeiro para o último tiro"
- Comparar dois treinos na mesma rota, com ghost lap mostrando onde ganhou e perdeu tempo
- Watcher de arquivos para importar assim que o `.fit` cair na pasta
