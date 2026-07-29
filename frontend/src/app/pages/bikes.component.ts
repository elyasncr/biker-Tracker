import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../core/api.service';
import { Bike, DrivetrainPresets, UnassignedGroup } from '../core/models';
import { NumPipe, RideDatePipe } from '../shared/format.pipe';

@Component({
  selector: 'app-bikes',
  standalone: true,
  imports: [FormsModule, RouterLink, NumPipe, RideDatePipe],
  template: `
    <section class="section">
      <div class="section-head">
        <h1>Garagem</h1>
        <span class="hint">{{ bikes().length }} bike(s)</span>
      </div>

      <div class="notice">
        <strong>Como o sistema sabe qual bike você usou.</strong> Cada sensor grava um número de rádio único dentro
        do .fit. Se os sensores moram numa bike só, esse conjunto identifica a bike e o reconhecimento vira
        automático: você nomeia uma vez e os treinos antigos ganham dono junto.
        <br /><br />
        Se você passa os mesmos sensores de uma bike para outra, a assinatura identifica os sensores, não a bike.
        O sistema percebe isso sozinho no momento em que a mesma assinatura for reivindicada por duas bikes: ele
        desliga o palpite automático para elas e passa a pedir atribuição manual. Errar em silêncio seria pior do
        que perguntar. Para esse caso existe a <strong>atribuição por período</strong> logo abaixo, que resolve
        vários pedais de uma vez.
      </div>

      <div class="notice">
        <strong>Por que o peso e o tipo importam.</strong> Sem potenciômetro, a potência dos seus treinos é calculada
        pela física — e peso, pneu e postura entram direto na conta. Uma MTB de 13 kg com pneu cravado gasta bem mais
        watt que uma speed de 8 kg na mesma velocidade. Preencher esses campos deixa a estimativa mais honesta.
      </div>

      @if (bikes().length) {
        <div class="grid cols-3" style="margin-bottom:32px">
          @for (bike of bikes(); track bike.id) {
            <article class="card bike">
              <header>
                <span class="eyebrow">{{ bike.kind }}</span>
                @if (bike.is_default) { <span class="badge">padrão</span> }
              </header>
              <h2>{{ bike.name }}</h2>
              <p class="context">
                {{ bike.brand }} {{ bike.model }} @if (bike.year) { · {{ bike.year }} }
                @if (bike.weight_kg) { · {{ bike.weight_kg }} kg }
              </p>
              @if (bike.chainrings?.length && bike.cassette?.length) {
                <p class="dentes" style="margin: 0 0 10px">
                  {{ bike.chainrings!.join('-') }} × {{ bike.cassette![0] }}-{{ bike.cassette![bike.cassette!.length - 1] }}
                  ({{ bike.chainrings!.length * bike.cassette!.length }} marchas)
                </p>
              }

              <div class="odo">
                <div>
                  <span class="label">Rodados</span>
                  <span class="value">{{ bike.stats.distance_km | num: 0 }}</span><span class="unit">km</span>
                </div>
                <div>
                  <span class="label">Pedais</span>
                  <span class="value">{{ bike.stats.activities }}</span>
                </div>
                <div>
                  <span class="label">Subidos</span>
                  <span class="value">{{ bike.stats.elevation_gain_m | num: 0 }}</span><span class="unit">m</span>
                </div>
              </div>

              <p class="hint">
                @if (bike.stats.last_ride) { Último uso: {{ bike.stats.last_ride | rideDate: false }}. }
                @if (bike.signatures.length) {
                  Reconhece sozinha por {{ bike.signatures.length }} conjunto(s) de sensores.
                } @else {
                  Ainda sem sensores aprendidos — atribua um treino a ela abaixo.
                }
              </p>

              <div style="display:flex; gap:8px">
                <button class="btn ghost" (click)="editar(bike)">Editar</button>
                <button class="btn ghost" (click)="remove(bike)">Remover</button>
              </div>
            </article>
          }
        </div>
      }

      <!-- Cadastro -->
      <div class="card" style="margin-bottom:32px">
        <h2>{{ editandoId() ? 'Editar bike' : 'Adicionar bike' }}</h2>
        <div class="form">
          <label>Nome<input [(ngModel)]="draft.name" placeholder="Speed de treino" /></label>
          <label>Marca<input [(ngModel)]="draft.brand" placeholder="Caloi" /></label>
          <label>Modelo<input [(ngModel)]="draft.model" placeholder="Strada Racing" /></label>
          <label>Ano<input type="number" [(ngModel)]="draft.year" /></label>
          <label>
            Tipo
            <select [(ngModel)]="draft.kind">
              <option value="speed">Speed</option>
              <option value="mtb">MTB</option>
              <option value="gravel">Gravel</option>
              <option value="urbana">Urbana</option>
            </select>
          </label>
          <label>Peso (kg)<input type="number" step="0.1" [(ngModel)]="draft.weight_kg" /></label>
          <label>
            Crr (atrito do pneu)
            <input type="number" step="0.001" [(ngModel)]="draft.crr" placeholder="automático pelo tipo" />
          </label>
          <label>
            CdA (arrasto do ar)
            <input type="number" step="0.01" [(ngModel)]="draft.cda" placeholder="automático pelo tipo" />
          </label>
          <label>
            Coroa
            <select [ngModel]="coroaPreset()" (ngModelChange)="aplicarCoroa($event)">
              <option [ngValue]="null">— escolha —</option>
              @for (p of presets()?.chainrings ?? []; track p.label) {
                <option [ngValue]="p.label">{{ p.label }}</option>
              }
            </select>
          </label>
          <label>
            Catraca
            <select [ngModel]="catracaPreset()" (ngModelChange)="aplicarCatraca($event)">
              <option [ngValue]="null">— escolha —</option>
              @for (p of presets()?.cassettes ?? []; track p.label) {
                <option [ngValue]="p.label">{{ p.label }}</option>
              }
            </select>
          </label>
          <label>
            Aro / pneu
            <select [ngModel]="aroPreset()" (ngModelChange)="aplicarAro($event)">
              <option [ngValue]="null">— escolha —</option>
              @for (p of presets()?.wheels ?? []; track p.label) {
                <option [ngValue]="p.label">{{ p.label }} ({{ p.value }} mm)</option>
              }
            </select>
          </label>
          <label class="check" style="grid-column: span 3">
            <span class="dentes">
              @if (draft.chainrings?.length) { Coroas: {{ draft.chainrings!.join(' · ') }} }
              @if (draft.cassette?.length) { &nbsp;|&nbsp; Cogs: {{ draft.cassette!.join(' · ') }} }
              @if (draft.wheel_circumference_mm) { &nbsp;|&nbsp; Aro: {{ draft.wheel_circumference_mm }} mm }
            </span>
            <button type="button" class="btn ghost" (click)="editarDentes.set(!editarDentes())">
              {{ editarDentes() ? 'fechar' : 'editar dentes na mão' }}
            </button>
          </label>
          @if (editarDentes()) {
            <label style="grid-column: span 3">
              Dentes das coroas (separados por vírgula)
              <input [ngModel]="coroasTexto()" (ngModelChange)="lerCoroas($event)" placeholder="42, 34, 24" />
            </label>
            <label style="grid-column: span 3">
              Dentes dos cogs (separados por vírgula, do menor pro maior)
              <input [ngModel]="cogsTexto()" (ngModelChange)="lerCogs($event)" placeholder="14, 16, 18, 20, 24, 28, 34" />
            </label>
          }
          <label class="check">
            <input type="checkbox" [(ngModel)]="draft.is_default" />
            Receber os treinos sem sensor identificado
          </label>
        </div>
        <div style="display:flex; gap:8px">
          <button class="btn" (click)="salvar()" [disabled]="!draft.name">
            {{ editandoId() ? 'Salvar alterações' : 'Salvar bike' }}
          </button>
          @if (editandoId()) {
            <button class="btn ghost" (click)="limparFormulario()">Cancelar</button>
          }
        </div>
      </div>

      <!-- Atribuicao por periodo -->
      @if (bikes().length) {
        <div class="card" style="margin-bottom:20px">
          <h2>Atribuir um período inteiro</h2>
          <p class="hint">
            Quando os sensores viajam entre bikes, sua memória é o dado mais confiável — e ela funciona por período,
            não pedal por pedal.
          </p>
          <div class="range">
            <label>De<input type="date" [(ngModel)]="rangeStart" /></label>
            <label>Ate<input type="date" [(ngModel)]="rangeEnd" /></label>
            <label>
              Bike
              <select [(ngModel)]="rangeBikeId">
                @for (bike of bikes(); track bike.id) {
                  <option [value]="bike.id">{{ bike.name }}</option>
                }
              </select>
            </label>
            <button class="btn" (click)="applyRange()" [disabled]="!rangeStart || !rangeEnd">Atribuir período</button>
          </div>
        </div>
      }

      <!-- Treinos sem dono -->
      <div class="section-head"><h2>Treinos sem bike</h2></div>
      @if (!groups().length) {
        <div class="empty">
          <h2>Todos os pedais têm dono</h2>
          <p>Nenhum treino esperando identificação.</p>
        </div>
      } @else {
        @for (group of groups(); track group.signature) {
          <div class="card" style="margin-bottom:14px">
            <div class="group-head">
              <div>
                <strong>{{ group.count }} treino(s)</strong>
                <span class="context">
                  @if (group.signature) {
                    sensores {{ group.signature }} — atribuir um resolve o grupo inteiro
                  } @else {
                    sem sensores no arquivo — a detecção automática não funciona aqui
                  }
                </span>
              </div>
              @if (bikes().length) {
                <div class="assign">
                  <select #picker>
                    @for (bike of bikes(); track bike.id) {
                      <option [value]="bike.id">{{ bike.name }}</option>
                    }
                  </select>
                  <button class="btn" (click)="assign(+picker.value, group.sample_activity_id)">Atribuir</button>
                </div>
              } @else {
                <span class="hint">Cadastre uma bike primeiro.</span>
              }
            </div>
            <div class="rides">
              @for (ride of group.rides; track ride.id) {
                <a [routerLink]="['/treinos', ride.id]">{{ ride.title }}</a>
              }
              @if (group.count > group.rides.length) {
                <span class="hint">e mais {{ group.count - group.rides.length }}…</span>
              }
            </div>
          </div>
        }
      }

      @if (message()) { <div class="notice">{{ message() }}</div> }
    </section>
  `,
  styles: [
    `
      .bike header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
      .badge {
        font-family: var(--body);
        font-size: 0.6rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        background: var(--ink);
        color: var(--paper);
        padding: 3px 7px;
        border-radius: 2px;
      }
      .context { font-size: 0.82rem; color: var(--secondary); margin: 0 0 14px; }
      .dentes { font-family: var(--body); font-size: 0.72rem; color: var(--secondary); text-transform: none; letter-spacing: 0; }
      .odo { display: flex; gap: 18px; border-top: 1px solid var(--rule); padding-top: 12px; margin-bottom: 10px; }
      .odo .label {
        display: block;
        font-family: var(--body);
        font-size: 0.6rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: var(--secondary);
      }
      .odo .value { font-family: var(--display); font-size: 1.5rem; }
      .odo .unit { font-family: var(--body); font-size: 0.7rem; color: var(--secondary); margin-left: 2px; }
      .form { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px; }
      .form label {
        display: flex;
        flex-direction: column;
        gap: 4px;
        font-family: var(--body);
        font-size: 0.65rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: var(--secondary);
      }
      .form input,
      .form select {
        font-family: var(--body);
        font-size: 0.95rem;
        text-transform: none;
        letter-spacing: 0;
        color: var(--ink);
        border: 1px solid var(--rule);
        border-radius: var(--radius);
        padding: 8px 10px;
        background: #fff;
      }
      .form .check { flex-direction: row; align-items: center; gap: 8px; grid-column: span 3; }
      .form .check input { width: auto; }
      .group-head { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; margin-bottom: 10px; }
      .group-head .context { margin: 0 0 0 8px; display: inline; }
      .assign { margin-left: auto; display: flex; gap: 8px; }
      .assign select { border: 1px solid var(--rule); border-radius: var(--radius); padding: 8px 10px; }
      .rides { display: flex; gap: 14px; flex-wrap: wrap; font-size: 0.85rem; }
      .rides a { border-bottom: 1px solid var(--rule); }
      .range { display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap; }
      .range label {
        display: flex;
        flex-direction: column;
        gap: 4px;
        font-family: var(--body);
        font-size: 0.65rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: var(--secondary);
      }
      .range input,
      .range select {
        font-family: var(--body);
        font-size: 0.95rem;
        text-transform: none;
        letter-spacing: 0;
        color: var(--ink);
        border: 1px solid var(--rule);
        border-radius: var(--radius);
        padding: 8px 10px;
        background: #fff;
      }
      @media (max-width: 700px) {
        .form { grid-template-columns: 1fr; }
        .form .check { grid-column: span 1; }
      }
    `,
  ],
})
export class BikesComponent implements OnInit {
  private api = inject(ApiService);

  bikes = signal<Bike[]>([]);
  groups = signal<UnassignedGroup[]>([]);
  message = signal('');

  draft: Partial<Bike> = { kind: 'speed', is_default: false };
  rangeStart = '';
  rangeEnd = '';
  rangeBikeId: number | null = null;

  presets = signal<DrivetrainPresets | null>(null);
  editarDentes = signal(false);
  editandoId = signal<number | null>(null);
  coroaPreset = signal<string | null>(null);
  catracaPreset = signal<string | null>(null);
  aroPreset = signal<string | null>(null);

  ngOnInit(): void {
    this.load();
    this.api.drivetrainPresets().subscribe((data) => this.presets.set(data));
  }

  private load(): void {
    this.api.bikes().subscribe((data) => this.bikes.set(data));
    this.api.unassigned().subscribe((data) => this.groups.set(data));
  }

  aplicarCoroa(label: string | null): void {
    this.coroaPreset.set(label);
    this.draft.chainrings = this.presets()?.chainrings.find((p) => p.label === label)?.value ?? null;
  }

  aplicarCatraca(label: string | null): void {
    this.catracaPreset.set(label);
    this.draft.cassette = this.presets()?.cassettes.find((p) => p.label === label)?.value ?? null;
  }

  aplicarAro(label: string | null): void {
    this.aroPreset.set(label);
    this.draft.wheel_circumference_mm =
      this.presets()?.wheels.find((p) => p.label === label)?.value ?? null;
  }

  coroasTexto(): string {
    return (this.draft.chainrings ?? []).join(', ');
  }

  cogsTexto(): string {
    return (this.draft.cassette ?? []).join(', ');
  }

  /** Editar na mao desliga o preset: a lista de dentes e a fonte da verdade. */
  lerCoroas(texto: string): void {
    this.draft.chainrings = this.lerNumeros(texto);
    this.coroaPreset.set(null);
  }

  lerCogs(texto: string): void {
    this.draft.cassette = this.lerNumeros(texto);
    this.catracaPreset.set(null);
  }

  private lerNumeros(texto: string): number[] | null {
    const numeros = texto
      .split(',')
      .map((p) => Number(p.trim()))
      .filter((n) => Number.isFinite(n) && n > 0);
    return numeros.length ? numeros : null;
  }

  editar(bike: Bike): void {
    this.editandoId.set(bike.id);
    // Copia, nao referencia: editar o formulario nao deve mexer no card antes de salvar.
    this.draft = { ...bike };
    this.editarDentes.set(false);
    // Reencontra o preset a partir dos dentes, para os selects nao ficarem vazios.
    const p = this.presets();
    this.coroaPreset.set(
      p?.chainrings.find((x) => this.mesmaLista(x.value, bike.chainrings))?.label ?? null,
    );
    this.catracaPreset.set(
      p?.cassettes.find((x) => this.mesmaLista(x.value, bike.cassette))?.label ?? null,
    );
    this.aroPreset.set(
      p?.wheels.find((x) => x.value === bike.wheel_circumference_mm)?.label ?? null,
    );
    window.scrollTo({ top: document.body.scrollHeight / 2, behavior: 'smooth' });
  }

  salvar(): void {
    const id = this.editandoId();
    const done = () => {
      this.message.set(
        id ? 'Bike atualizada.' : 'Bike cadastrada. Agora atribua um treino a ela para ensinar os sensores.',
      );
      this.limparFormulario();
      this.load();
    };
    if (id) {
      this.api.updateBike(id, this.draft).subscribe(done);
    } else {
      this.api.createBike(this.draft).subscribe(done);
    }
  }

  limparFormulario(): void {
    this.editandoId.set(null);
    this.draft = { kind: 'speed', is_default: false };
    this.coroaPreset.set(null);
    this.catracaPreset.set(null);
    this.aroPreset.set(null);
    this.editarDentes.set(false);
  }

  private mesmaLista(a: number[], b: number[] | null | undefined): boolean {
    return !!b && a.length === b.length && a.every((v, i) => v === b[i]);
  }

  assign(bikeId: number, activityId: number): void {
    this.api.claim(bikeId, activityId).subscribe((result) => {
      this.message.set(result.message);
      this.load();
    });
  }

  applyRange(): void {
    const bikeId = Number(this.rangeBikeId ?? this.bikes()[0]?.id);
    if (!bikeId || !this.rangeStart || !this.rangeEnd) {
      return;
    }
    this.api
      .assignRange(bikeId, this.rangeStart + 'T00:00:00', this.rangeEnd + 'T23:59:59')
      .subscribe((result) => {
        this.message.set(result.message);
        this.load();
      });
  }

  remove(bike: Bike): void {
    if (!confirm('Remover ' + bike.name + '? Os treinos dela voltam a ficar sem bike.')) {
      return;
    }
    this.api.deleteBike(bike.id).subscribe(() => this.load());
  }
}
