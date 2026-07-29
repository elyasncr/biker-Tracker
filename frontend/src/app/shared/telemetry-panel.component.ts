import { Component, Input } from '@angular/core';
import { ChartConfiguration } from 'chart.js';
import { Analysis, ClimbComparison, GearCoverage, SegmentHighlight } from '../core/models';
import { ChartComponent } from './chart.component';
import { DurationPipe, NumPipe } from './format.pipe';

@Component({
  selector: 'app-telemetry',
  standalone: true,
  imports: [ChartComponent, DurationPipe, NumPipe],
  template: `
    @if (!analysis?.available) {
      <div class="notice">{{ analysis?.reason ?? 'Sem dados suficientes para a analise por trechos.' }}</div>
    } @else {
      <!-- Melhor e pior trecho, lado a lado, como o quadro de setores de uma corrida -->
      <div class="grid cols-2" style="margin-bottom:20px">
        @if (best(); as seg) {
          <article class="moment good">
            <header>
              <span class="tag">Melhor momento</span>
              <span class="delta">{{ seg.score - 100 | num: 0 }}%</span>
            </header>
            <h3>km {{ seg.start_km | num: 1 }} a {{ seg.end_km | num: 1 }}</h3>
            <p class="context">
              {{ seg.terrain }} de {{ seg.gradient | num: 1 }}% · {{ seg.distance_m | num: 0 }} m ·
              {{ seg.duration_s | duration }}
            </p>
            <ul>
              @for (reason of seg.reasons; track reason.text) {
                <li><span class="kind">{{ reason.kind }}</span>{{ reason.text }}</li>
              }
            </ul>
          </article>
        }
        @if (worst(); as seg) {
          <article class="moment bad">
            <header>
              <span class="tag">Pior momento</span>
              <span class="delta">{{ seg.score - 100 | num: 0 }}%</span>
            </header>
            <h3>km {{ seg.start_km | num: 1 }} a {{ seg.end_km | num: 1 }}</h3>
            <p class="context">
              {{ seg.terrain }} de {{ seg.gradient | num: 1 }}% · {{ seg.distance_m | num: 0 }} m ·
              {{ seg.duration_s | duration }}
            </p>
            <ul>
              @for (reason of seg.reasons; track reason.text) {
                <li><span class="kind">{{ reason.kind }}</span>{{ reason.text }}</li>
              }
            </ul>
          </article>
        }
      </div>

      <p class="footnote">
        A comparacao e sempre voce contra voce, no mesmo dia: mesmo vento, mesma perna, mesma estrada. Descidas
        ficam de fora — elas medem a estrada, nao voce. Base usada neste treino: <strong>{{ analysis!.basis }}</strong>.
        @if (!analysis!.has_hr) {
          Sem cinta cardiaca, nao ha como medir o custo do esforco — entao a nota mede
          <strong>resultado</strong>, e vento e semaforo entram na conta junto com a sua perna.
        }
      </p>

      <!-- Ritmo pelo quarto do pedal -->
      @if (analysis!.pacing.available) {
        <div class="card" style="margin:20px 0">
          <h2>Gestao de esforco</h2>
          <p>{{ analysis!.pacing.verdict }}</p>
          <div class="quarters">
            @for (value of analysis!.pacing.quarters ?? []; track $index) {
              <div class="quarter">
                <span class="label">{{ $index + 1 }}º quarto</span>
                <span class="value">{{ value | num: 0 }}</span>
                <span class="unit">{{ analysis!.pacing.unit }}</span>
              </div>
            }
          </div>
        </div>
      }

      <!-- Cadencia -->
      @if (analysis!.cadence.available) {
        <div class="grid cols-2" style="margin-bottom:20px">
          <div class="card">
            <h2>Cadencia</h2>
            <div class="chart-box">
              @if (cadenceChart(); as cfg) { <app-chart [config]="cfg" /> }
            </div>
          </div>
          <div class="card">
            <h2>Leitura do giro</h2>
            <div class="grid cols-2" style="gap:12px; margin-bottom:14px">
              <div class="plate">
                <span class="label">Giro medio</span>
                <span class="value">{{ analysis!.cadence.avg_rpm | num: 0 }}</span><span class="unit">rpm</span>
              </div>
              <div class="plate">
                <span class="label">Torque medio</span>
                <span class="value">{{ analysis!.cadence.avg_torque_nm | num: 0 }}</span><span class="unit">Nm</span>
              </div>
            </div>
            <p>{{ analysis!.cadence.insight }}</p>
            <table style="margin-top:12px">
              <tbody>
                @for (item of terrainRows(); track item.terrain) {
                  <tr>
                    <td>Giro em {{ item.terrain }}</td>
                    <td class="num mono">{{ item.rpm | num: 0 }} rpm</td>
                  </tr>
                }
                <tr>
                  <td>Tempo de barriga (sem pedalar)</td>
                  <td class="num mono">{{ analysis!.cadence.coasting_s | duration }}</td>
                </tr>
                @if (analysis!.cadence.mashing_s > 0) {
                  <tr>
                    <td>Marcha pesada com forca alta</td>
                    <td class="num mono">{{ analysis!.cadence.mashing_s | duration }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        </div>
      }

      <!-- Marchas: o que velocidade + cadencia entregam sem sensor extra -->
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

      <!-- Subidas comparadas com o historico -->
      @if (climbs.length) {
        <div class="card" style="margin-bottom:20px">
          <h2>Suas subidas contra o historico</h2>
          @for (climb of climbs; track climb.segment.start_km) {
            <div class="climb">
              <div>
                <strong>km {{ climb.segment.start_km | num: 1 }}</strong>
                <span class="context">
                  {{ climb.segment.distance_m | num: 0 }} m a {{ climb.segment.gradient | num: 1 }}% ·
                  {{ climb.segment.duration_s | duration }}
                </span>
              </div>
              <span class="verdict" [class.faster]="climb.delta_s < 0">{{ climb.verdict }}</span>
            </div>
          }
        </div>
      }

      <!-- Parciais por km, igual tabela de voltas -->
      @if (analysis!.splits.length) {
        <div class="card">
          <h2>Parciais por quilometro</h2>
          <div class="chart-box" style="margin-bottom:16px">
            @if (splitChart(); as cfg) { <app-chart [config]="cfg" /> }
          </div>
          <table>
            <thead>
              <tr>
                <th>Km</th>
                <th class="num">Tempo</th>
                <th class="num">km/h</th>
                <th class="num">Subida</th>
                <th class="num">FC</th>
                <th class="num">W</th>
                <th class="num">rpm</th>
              </tr>
            </thead>
            <tbody>
              @for (split of analysis!.splits; track split.km) {
                <tr>
                  <td class="mono">{{ split.km }}</td>
                  <td class="num mono">{{ split.duration_s | duration }}</td>
                  <td class="num mono">{{ split.speed_kmh | num: 1 }}</td>
                  <td class="num mono">{{ split.elevation_m | num: 0 }} m</td>
                  <td class="num mono">{{ split.avg_hr | num: 0 }}</td>
                  <td class="num mono">{{ split.avg_power | num: 0 }}</td>
                  <td class="num mono">{{ split.avg_cadence | num: 0 }}</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }
    }
  `,
  styles: [
    `
      .moment {
        background: #fff;
        border: 1px solid var(--rule);
        border-left: 4px solid var(--graphite);
        border-radius: var(--radius);
        padding: 18px;
      }
      .moment.good { border-left-color: var(--climb); }
      .moment.bad { border-left-color: var(--pulse); }
      .moment header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 6px; }
      .tag {
        font-family: var(--mono);
        font-size: 0.65rem;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        color: var(--graphite);
      }
      .delta {
        margin-left: auto;
        font-family: var(--display);
        font-size: 1.5rem;
        line-height: 1;
      }
      .good .delta { color: var(--climb); }
      .bad .delta { color: var(--pulse); }
      .moment h3 { font-family: var(--display); font-size: 1.5rem; font-weight: 400; margin: 0; }
      .context { font-size: 0.8rem; color: var(--graphite); margin: 2px 0 12px; }
      .moment ul { list-style: none; margin: 0; padding: 0; }
      .moment li {
        font-size: 0.88rem;
        line-height: 1.5;
        padding: 10px 0;
        border-top: 1px solid var(--rule);
      }
      .kind {
        display: block;
        font-family: var(--mono);
        font-size: 0.6rem;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: var(--graphite);
        margin-bottom: 3px;
      }
      .footnote {
        font-size: 0.8rem;
        color: var(--graphite);
        border-left: 2px solid var(--rule);
        padding-left: 12px;
        margin: 0;
      }
      .quarters { display: flex; gap: 10px; margin-top: 14px; flex-wrap: wrap; }
      .quarter {
        flex: 1;
        min-width: 90px;
        border-top: 2px solid var(--ink);
        padding-top: 6px;
      }
      .quarter .label {
        display: block;
        font-family: var(--mono);
        font-size: 0.62rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: var(--graphite);
      }
      .quarter .value { font-family: var(--display); font-size: 1.6rem; }
      .quarter .unit { font-family: var(--mono); font-size: 0.72rem; color: var(--graphite); margin-left: 3px; }
      .climb {
        display: flex;
        align-items: center;
        gap: 14px;
        flex-wrap: wrap;
        padding: 12px 0;
        border-bottom: 1px solid var(--rule);
      }
      .climb .context { margin: 0 0 0 8px; display: inline; }
      .verdict { margin-left: auto; font-size: 0.85rem; color: var(--pulse); }
      .verdict.faster { color: var(--climb); }
    `,
  ],
})
export class TelemetryComponent {
  @Input() analysis: Analysis | null = null;
  @Input() climbs: ClimbComparison[] = [];

  best(): SegmentHighlight | null {
    return this.analysis?.highlights?.best ?? null;
  }

  worst(): SegmentHighlight | null {
    return this.analysis?.highlights?.worst ?? null;
  }

  terrainRows(): { terrain: string; rpm: number }[] {
    const byTerrain = this.analysis?.cadence?.by_terrain ?? {};
    return Object.entries(byTerrain).map(([terrain, rpm]) => ({ terrain, rpm }));
  }

  coverage(): GearCoverage | null {
    return this.analysis?.gears?.coverage ?? null;
  }

  cadenceChart(): ChartConfiguration | null {
    const bands = this.analysis?.cadence?.bands;
    if (!bands?.length) {
      return null;
    }
    return {
      type: 'bar',
      data: {
        labels: bands.map((b) => b.band),
        datasets: [
          {
            label: 'minutos',
            data: bands.map((b) => Math.round((b.seconds / 60) * 10) / 10),
            // Faixas muito baixas ganham destaque: sao as que castigam a articulacao.
            backgroundColor: bands.map((b) => (b.rpm_low < 70 ? '#b81d4c' : '#2e7d6b')),
            borderRadius: 2,
          },
        ],
      },
      options: {
        indexAxis: 'y',
        plugins: { legend: { display: false } },
        scales: { x: { title: { display: true, text: 'minutos' } } },
      },
    };
  }

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
            // Os picos sao as marchas favoritas: ganham destaque.
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

  splitChart(): ChartConfiguration | null {
    const splits = this.analysis?.splits;
    if (!splits?.length) {
      return null;
    }
    return {
      type: 'bar',
      data: {
        labels: splits.map((s) => 'km ' + s.km),
        datasets: [
          {
            type: 'bar',
            label: 'Velocidade (km/h)',
            data: splits.map((s) => s.speed_kmh),
            backgroundColor: 'rgba(14,31,43,0.8)',
            borderRadius: 2,
            yAxisID: 'y',
          },
          {
            type: 'line',
            label: 'Subida no km (m)',
            data: splits.map((s) => s.elevation_m),
            borderColor: '#2e7d6b',
            backgroundColor: 'rgba(46,125,107,0.14)',
            fill: true,
            pointRadius: 0,
            borderWidth: 1.5,
            yAxisID: 'y1',
          },
        ],
      },
      options: {
        scales: {
          y: { title: { display: true, text: 'km/h' } },
          y1: { position: 'right', grid: { display: false }, title: { display: true, text: 'm' } },
          x: { ticks: { maxTicksLimit: 20 }, grid: { display: false } },
        },
      },
    };
  }
}
