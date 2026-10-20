import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ChartConfiguration } from 'chart.js';
import { ApiService } from '../core/api.service';
import { CoachGoal, CoachInsight, CoachReading } from '../core/models';
import { ChartComponent } from '../shared/chart.component';
import { NumPipe } from '../shared/format.pipe';
import { INK, INK_FILL, SECONDARY } from '../core/theme';
import { buildBars, buildPacing, cadenceColors, TERRAIN_COLORS, ZONE_COLOR } from '../shared/insight-charts';

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

        <div class="insight">
          <span class="eyebrow">Análise do treinador</span>
          @if (insightLoading()) {
            <p class="lead loading">Lendo seus pedais com IA local…</p>
          } @else if (insight()?.text?.overall) {
            <p class="lead">{{ insight()?.text?.overall }}</p>
            <div class="insight-foot">
              <span class="hint">IA local · {{ insight()?.model }}</span>
              <button class="btn ghost" (click)="recarregarInsight()">Atualizar análise</button>
            </div>
          } @else {
            <p class="hint">{{ insight()?.reason ?? 'Análise indisponível — confira se o Ollama está rodando.' }}</p>
          }
        </div>

        <div class="card ready">
          <span class="eyebrow">Hoje</span>
          <h2 class="big">{{ d.readiness.headline }}</h2>
          <p>{{ d.readiness.detail }}</p>
        </div>

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

        <div class="section-head" style="margin-top:24px; margin-bottom:0; border-bottom:0">
          <h2>Progresso</h2>
          <span class="hint">constância primeiro — é dela que vem o resto</span>
        </div>

        <div class="grid cols-2">
          <div class="card">
            <h2>Constância</h2>
            @if (consistencyChart(); as cfg) {
              <div class="chart-box" style="height:180px"><app-chart [config]="cfg" /></div>
            } @else {
              <p class="hint">Nenhuma semana com treino ainda.</p>
            }
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
              @if (weightChart(); as cfg) {
                <div class="chart-box" style="height:180px"><app-chart [config]="cfg" /></div>
              }
            } @else {
              <p class="hint">
                Nenhum peso registrado ainda. Lance o primeiro abaixo — ele destrava a linha de
                tendência e corrige o cálculo de potência, que hoje usa um valor fixo.
              </p>
            }
          </div>
        </div>

        @if (insight()?.summary; as sum) {
          <div class="section-head" style="margin-top:28px; margin-bottom:0; border-bottom:0">
            <h2>Pontos pra evoluir</h2>
            <span class="hint">{{ sum.rides_analyzed }} pedais lidos · leitura do .fit</span>
          </div>

          <div class="grid cols-2">
            <div class="card">
              <h2>Cadência</h2>
              @if (cadenceChart(); as cfg) {
                <div class="chart-box" style="height:170px"><app-chart [config]="cfg" /></div>
              }
              @if (insight()?.text?.cadencia; as t) { <p class="tip">{{ t }}</p> }
            </div>
            <div class="card">
              <h2>Pacing</h2>
              @if (pacingChart(); as cfg) {
                <div class="chart-box" style="height:170px"><app-chart [config]="cfg" /></div>
              }
              @if (insight()?.text?.pacing; as t) { <p class="tip">{{ t }}</p> }
            </div>
            <div class="card">
              <h2>Zonas de potência</h2>
              @if (zonesChart(); as cfg) {
                <div class="chart-box" style="height:170px"><app-chart [config]="cfg" /></div>
              }
              @if (insight()?.text?.zonas; as t) { <p class="tip">{{ t }}</p> }
            </div>
            <div class="card">
              <h2>Terreno</h2>
              @if (terrainChart(); as cfg) {
                <div class="chart-box" style="height:170px"><app-chart [config]="cfg" /></div>
              }
              @if (insight()?.text?.terreno; as t) { <p class="tip">{{ t }}</p> }
            </div>
          </div>
        }

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
          @if (aviso()) { <p class="hint" style="margin-top:10px">{{ aviso() }}</p> }
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
      .ready { margin-bottom: 20px; }
      .insight { border-top: 1px solid var(--rule); padding: 16px 0 20px; }
      .insight .lead {
        font-family: var(--display); font-size: 1.15rem; line-height: 1.5;
        color: var(--ink); margin: 8px 0 0; max-width: 60ch;
      }
      .insight .lead.loading { color: var(--secondary); font-style: italic; }
      .insight-foot {
        display: flex; align-items: center; gap: 14px; margin-top: 12px; flex-wrap: wrap;
      }
      /* Comentario da IA abaixo de cada grafico: filete na cor da tinta a esquerda. */
      .tip {
        margin: 12px 0 0; padding-left: 12px; border-left: 2px solid var(--rule);
        font-size: 0.9rem; line-height: 1.5; color: var(--secondary);
      }
      .big { font-size: 1.6rem; text-transform: none; letter-spacing: 0; margin-bottom: 8px; }
      .linha { display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap; }
      .linha label {
        display: flex; flex-direction: column; gap: 4px;
        font-family: var(--body); font-size: 0.65rem; letter-spacing: 0.12em;
        text-transform: uppercase; color: var(--secondary);
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
  // Config dos graficos vive em signal (referencia estavel), igual ao detalhe do
  // treino. Como metodo chamado no template, o Angular criava um objeto novo a
  // cada ciclo e o app-chart recriava o Chart.js sem parar, deixando tudo em branco.
  consistencyChart = signal<ChartConfiguration | null>(null);
  weightChart = signal<ChartConfiguration | null>(null);

  // Insight do treinador (Ollama). Carrega em separado porque e lento; a tela
  // nao espera por ele. Os graficos saem dos numeros; o texto e best-effort.
  insight = signal<CoachInsight | null>(null);
  insightLoading = signal(true);
  cadenceChart = signal<ChartConfiguration | null>(null);
  zonesChart = signal<ChartConfiguration | null>(null);
  pacingChart = signal<ChartConfiguration | null>(null);
  terrainChart = signal<ChartConfiguration | null>(null);

  aviso = signal('');
  novoPeso: number | null = null;
  metaPedais = 3;
  metaMinutos = 180;

  ngOnInit(): void {
    this.carregar();
    this.carregarInsight();
  }

  private carregarInsight(refresh = false): void {
    this.insightLoading.set(true);
    this.api.coachInsight(refresh).subscribe({
      next: (ins) => {
        this.insight.set(ins);
        if (ins.summary) {
          this.cadenceChart.set(buildBars(ins.summary.cadence.seconds, cadenceColors(ins.summary)));
          this.zonesChart.set(buildBars(ins.summary.zones.seconds, ZONE_COLOR));
          this.pacingChart.set(buildPacing(ins.summary));
          this.terrainChart.set(buildBars(ins.summary.terrain.seconds, TERRAIN_COLORS));
        }
        this.insightLoading.set(false);
      },
      error: () => {
        this.insight.set({ available: false, text: null, reason: 'Análise indisponível agora.' });
        this.insightLoading.set(false);
      },
    });
  }

  recarregarInsight(): void {
    this.carregarInsight(true);
  }


  private carregar(): void {
    this.api.coach().subscribe((d) => {
      this.data.set(d);
      this.consistencyChart.set(this.buildConsistency(d));
      this.weightChart.set(this.buildWeight(d));
      this.metaPedais = d.goal.rides_per_week;
      this.metaMinutos = d.goal.minutes_per_week;
    });
  }

  lancarPeso(): void {
    if (!this.novoPeso) {
      return;
    }
    // Data local, nao UTC: toISOString() converte para UTC e depois das 21h no
    // Brasil isso gravaria a pesagem no dia seguinte - que o backend rejeita.
    const hoje = new Date();
    const iso = `${hoje.getFullYear()}-${String(hoje.getMonth() + 1).padStart(2, '0')}-${String(hoje.getDate()).padStart(2, '0')}`;
    this.api.logWeight(iso, this.novoPeso).subscribe({
      next: () => {
        this.novoPeso = null;
        this.aviso.set('Peso registrado.');
        this.carregar();
      },
      error: (e) => this.aviso.set('Não deu para registrar: ' + (e.error?.detail?.[0]?.msg ?? 'valor inválido')),
    });
  }

  salvarMeta(): void {
    const goal: CoachGoal = {
      rides_per_week: this.metaPedais,
      minutes_per_week: this.metaMinutos,
      target_weight_kg: this.data()?.goal.target_weight_kg ?? null,
    };
    this.api.setGoal(goal).subscribe({
      next: () => {
        this.aviso.set('Meta salva.');
        this.carregar();
      },
      error: (e) => this.aviso.set('Meta inválida: ' + (e.error?.detail?.[0]?.msg ?? 'confira os valores')),
    });
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

  private buildConsistency(d: CoachReading): ChartConfiguration | null {
    const weeks = d.progress.consistency.weeks;
    if (!weeks?.length) {
      return null;
    }
    const meta = d.progress.consistency.goal_minutes;
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
            backgroundColor: weeks.map((w) => (w.met_goal ? INK : 'rgba(26,26,24,.30)')),
            borderRadius: 2,
          },
          {
            type: 'line',
            label: 'meta',
            data: weeks.map(() => meta),
            borderColor: SECONDARY,
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

  private buildWeight(d: CoachReading): ChartConfiguration | null {
    const w = d.progress.weight;
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
            borderColor: INK,
            backgroundColor: INK_FILL,
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
