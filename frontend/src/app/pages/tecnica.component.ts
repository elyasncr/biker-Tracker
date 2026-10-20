import { Component, OnInit, inject, signal } from '@angular/core';
import { ChartConfiguration } from 'chart.js';
import { ApiService } from '../core/api.service';
import { CoachEvolution } from '../core/models';
import { ChartComponent } from '../shared/chart.component';
import { buildBars, buildPacing, cadenceColors, TERRAIN_COLORS, ZONE_COLOR } from '../shared/insight-charts';

@Component({
  selector: 'app-tecnica',
  standalone: true,
  imports: [ChartComponent],
  template: `
    <section class="section">
      <div class="section-head">
        <h1>Pontos de evolução</h1>
        <span class="hint">dica, como melhorar e como aplicar no treino</span>
      </div>

      @if (loading()) {
        <p class="lead loading">Montando seu plano de evolução com IA local…</p>
      } @else if (evo()?.guide?.intro) {
        <p class="lead">{{ evo()?.guide?.intro }}</p>
        <div class="insight-foot">
          <span class="hint">IA local · {{ evo()?.model }} · {{ evo()?.summary?.rides_analyzed }} pedais lidos</span>
          <button class="btn ghost" (click)="recarregar()">Refazer plano</button>
        </div>
      } @else {
        <p class="hint">{{ evo()?.reason ?? 'Plano indisponível — confira se o Ollama está rodando.' }}</p>
      }

      @if (evo()?.summary) {
        <!-- Cada tópico: gráfico à esquerda, guia de 3 partes à direita. -->
        <div class="dim">
          <div class="dim-head"><h2>Cadência</h2></div>
          <div class="grid cols-2">
            <div class="card">
              @if (cadenceChart(); as cfg) { <div class="chart-box" style="height:200px"><app-chart [config]="cfg" /></div> }
            </div>
            <div class="card">
              @if (evo()?.guide?.cadencia; as g) {
                <p class="mostra">{{ g.mostra }}</p>
                <div class="part"><span class="plabel">Como melhorar</span><p>{{ g.melhorar }}</p></div>
                <div class="part treino"><span class="plabel">No próximo pedal</span><p>{{ g.treino }}</p></div>
              }
            </div>
          </div>
        </div>

        <div class="dim">
          <div class="dim-head"><h2>Pacing</h2></div>
          <div class="grid cols-2">
            <div class="card">
              @if (pacingChart(); as cfg) { <div class="chart-box" style="height:200px"><app-chart [config]="cfg" /></div> }
            </div>
            <div class="card">
              @if (evo()?.guide?.pacing; as g) {
                <p class="mostra">{{ g.mostra }}</p>
                <div class="part"><span class="plabel">Como melhorar</span><p>{{ g.melhorar }}</p></div>
                <div class="part treino"><span class="plabel">No próximo pedal</span><p>{{ g.treino }}</p></div>
              }
            </div>
          </div>
        </div>

        <div class="dim">
          <div class="dim-head"><h2>Zonas de potência</h2></div>
          <div class="grid cols-2">
            <div class="card">
              @if (zonesChart(); as cfg) { <div class="chart-box" style="height:200px"><app-chart [config]="cfg" /></div> }
            </div>
            <div class="card">
              @if (evo()?.guide?.zonas; as g) {
                <p class="mostra">{{ g.mostra }}</p>
                <div class="part"><span class="plabel">Como melhorar</span><p>{{ g.melhorar }}</p></div>
                <div class="part treino"><span class="plabel">No próximo pedal</span><p>{{ g.treino }}</p></div>
              }
            </div>
          </div>
        </div>

        <div class="dim">
          <div class="dim-head"><h2>Terreno</h2></div>
          <div class="grid cols-2">
            <div class="card">
              @if (terrainChart(); as cfg) { <div class="chart-box" style="height:200px"><app-chart [config]="cfg" /></div> }
            </div>
            <div class="card">
              @if (evo()?.guide?.terreno; as g) {
                <p class="mostra">{{ g.mostra }}</p>
                <div class="part"><span class="plabel">Como melhorar</span><p>{{ g.melhorar }}</p></div>
                <div class="part treino"><span class="plabel">No próximo pedal</span><p>{{ g.treino }}</p></div>
              }
            </div>
          </div>
        </div>
      }
    </section>
  `,
  styles: [
    `
      .lead {
        font-family: var(--display); font-size: 1.15rem; line-height: 1.5;
        color: var(--ink); margin: 4px 0 0; max-width: 62ch;
      }
      .lead.loading { color: var(--secondary); font-style: italic; }
      .insight-foot { display: flex; align-items: center; gap: 14px; margin-top: 12px; flex-wrap: wrap; }

      .dim { margin-top: 30px; }
      .dim-head { border-bottom: 1px solid var(--rule); padding-bottom: 8px; margin-bottom: 4px; }

      .mostra { margin: 0 0 4px; color: var(--ink); line-height: 1.5; }
      .part { margin-top: 14px; }
      .plabel {
        display: block; font-family: var(--body); font-size: 0.62rem; letter-spacing: 0.12em;
        text-transform: uppercase; color: var(--secondary); margin-bottom: 4px;
      }
      .part p { margin: 0; line-height: 1.55; color: var(--secondary); }
      /* O exercicio pratico ganha destaque: filete na cor da altimetria. */
      .part.treino { border-left: 2px solid var(--climb); padding-left: 12px; }
      .part.treino p { color: var(--ink); }
    `,
  ],
})
export class TecnicaComponent implements OnInit {
  private api = inject(ApiService);

  evo = signal<CoachEvolution | null>(null);
  loading = signal(true);
  cadenceChart = signal<ChartConfiguration | null>(null);
  zonesChart = signal<ChartConfiguration | null>(null);
  pacingChart = signal<ChartConfiguration | null>(null);
  terrainChart = signal<ChartConfiguration | null>(null);

  ngOnInit(): void {
    this.carregar();
  }

  recarregar(): void {
    this.carregar(true);
  }

  private carregar(refresh = false): void {
    this.loading.set(true);
    this.api.coachEvolution(refresh).subscribe({
      next: (e) => {
        this.evo.set(e);
        if (e.summary) {
          this.cadenceChart.set(buildBars(e.summary.cadence.seconds, cadenceColors(e.summary)));
          this.zonesChart.set(buildBars(e.summary.zones.seconds, ZONE_COLOR));
          this.pacingChart.set(buildPacing(e.summary));
          this.terrainChart.set(buildBars(e.summary.terrain.seconds, TERRAIN_COLORS));
        }
        this.loading.set(false);
      },
      error: () => {
        this.evo.set({ available: false, guide: null, reason: 'Plano indisponível agora.' });
        this.loading.set(false);
      },
    });
  }
}
