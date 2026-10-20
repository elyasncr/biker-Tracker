import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ChartConfiguration } from 'chart.js';
import { ApiService } from '../core/api.service';
import { ActivitySummary, CoachEvolution, RouteAdvice, RoutePoint } from '../core/models';
import { ChartComponent } from '../shared/chart.component';
import { AdviceMapComponent } from '../shared/advice-map.component';
import { NumPipe } from '../shared/format.pipe';
import { buildBars, buildPacing, cadenceColors, TERRAIN_COLORS, ZONE_COLOR } from '../shared/insight-charts';

@Component({
  selector: 'app-tecnica',
  standalone: true,
  imports: [ChartComponent, AdviceMapComponent, FormsModule, NumPipe],
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

      <!-- Mapa do percurso de um treino, com os 3 pontos de melhoria ancorados. -->
      <div class="percurso">
        <div class="section-head" style="margin-top:28px">
          <h2>Onde melhorar no percurso</h2>
          @if (rides().length) {
            <select class="ride-select" [ngModel]="selectedRideId()" (ngModelChange)="selectRide($event)">
              @for (r of rides(); track r.id) {
                <option [ngValue]="r.id">{{ r.title }} · {{ r.distance_km | num: 1 }} km</option>
              }
            </select>
          }
        </div>

        @if (routeLoading()) {
          <p class="lead loading">Lendo o percurso e apontando onde melhorar…</p>
        } @else if (advice()?.available && routePoints().length) {
          <div class="pmap">
            <app-advice-map
              [points]="routePoints()"
              [advice]="advice()!.points!"
              [active]="activeOrder()"
              (activeChange)="activeOrder.set($event)"
            />
            <div class="advice-list">
              @for (p of advice()!.points!; track p.order) {
                <div
                  class="advice-item"
                  [class.on]="p.order === activeOrder()"
                  (mouseenter)="activeOrder.set(p.order)"
                  (mouseleave)="activeOrder.set(null)"
                >
                  <div class="advice-head"><span class="num">{{ p.order }}</span><strong>{{ p.label }}</strong></div>
                  <p class="prob">{{ p.problema }}</p>
                  @if (p.dica) {
                    <p class="dica"><span class="plabel">Como melhorar aqui</span>{{ p.dica }}</p>
                  }
                </div>
              }
            </div>
          </div>
        } @else {
          <p class="hint">{{ advice()?.reason ?? 'Escolha um treino com GPS para ver o percurso.' }}</p>
        }
      </div>

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

      .ride-select {
        margin-left: auto; font-family: var(--body); font-size: 0.9rem; color: var(--ink);
        border: 1px solid var(--rule); border-radius: var(--radius); padding: 6px 10px; background: #fff;
      }
      .pmap { display: grid; grid-template-columns: 1.4fr 1fr; gap: 22px; align-items: start; }
      @media (max-width: 760px) { .pmap { grid-template-columns: 1fr; } }

      .advice-item {
        border-top: 1px solid var(--rule); padding: 12px 10px; cursor: default;
        transition: background 0.15s;
      }
      .advice-item:first-child { border-top: 0; }
      .advice-item.on { background: var(--paper-deep); }
      .advice-head { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
      .advice-head .num {
        flex: none; width: 22px; height: 22px; border-radius: 50%; background: var(--ink); color: var(--paper);
        font: 600 12px/1 'IBM Plex Mono', ui-monospace, monospace; display: flex; align-items: center; justify-content: center;
      }
      .advice-item.on .advice-head .num { background: var(--watt); }
      .advice-head strong { font-family: var(--display); font-size: 1rem; color: var(--ink); }
      .prob { margin: 0; font-size: 0.9rem; line-height: 1.5; color: var(--secondary); }
      .dica { margin: 10px 0 0; font-size: 0.9rem; line-height: 1.55; color: var(--ink); }
      .dica .plabel {
        display: block; font-family: var(--body); font-size: 0.62rem; letter-spacing: 0.12em;
        text-transform: uppercase; color: var(--watt); margin-bottom: 4px;
      }
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

  // Percurso de um treino: seletor, mapa e dicas ancoradas.
  rides = signal<ActivitySummary[]>([]);
  selectedRideId = signal<number | null>(null);
  routePoints = signal<RoutePoint[]>([]);
  advice = signal<RouteAdvice | null>(null);
  routeLoading = signal(false);
  activeOrder = signal<number | null>(null);

  ngOnInit(): void {
    this.carregar();
    this.carregarTreinos();
  }

  private carregarTreinos(): void {
    this.api.activities().subscribe((list) => {
      this.rides.set(list);
      if (list.length) {
        this.selectRide(list[0].id); // mais recente primeiro
      }
    });
  }

  selectRide(id: number): void {
    this.selectedRideId.set(id);
    this.activeOrder.set(null);
    this.routeLoading.set(true);
    this.routePoints.set([]);
    this.advice.set(null);
    // Rota e dicas em paralelo; a rota desenha o mapa, as dicas apontam os pontos.
    this.api.route(id).subscribe({
      next: (r) => this.routePoints.set(r.available ? r.points : []),
      error: () => this.routePoints.set([]),
    });
    this.api.routeAdvice(id).subscribe({
      next: (a) => {
        this.advice.set(a);
        this.routeLoading.set(false);
      },
      error: () => {
        this.advice.set({ available: false, reason: 'Análise do percurso indisponível agora.' });
        this.routeLoading.set(false);
      },
    });
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
