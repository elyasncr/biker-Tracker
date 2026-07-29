import { Component, OnInit, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { ApiService } from '../core/api.service';
import { ActivitySummary } from '../core/models';
import { DurationPipe, NumPipe, RideDatePipe } from '../shared/format.pipe';

@Component({
  selector: 'app-activities',
  standalone: true,
  imports: [RouterLink, DurationPipe, NumPipe, RideDatePipe],
  template: `
    <section class="section">
      <div class="section-head">
        <h1>Treinos</h1>
        <span class="hint">{{ rides().length }} registro(s)</span>
      </div>

      <div class="card" style="margin-bottom:20px; display:flex; align-items:center; gap:16px; flex-wrap:wrap">
        <div>
          <strong>Subir um .fit agora</strong>
          <div class="hint">O arquivo vai para a pasta data/ e é importado na hora.</div>
        </div>
        <input type="file" accept=".fit" (change)="upload($event)" style="margin-left:auto" />
      </div>

      @if (uploadMessage()) {
        <div class="notice">{{ uploadMessage() }}</div>
      }

      @if (rides().length === 0) {
        <div class="empty">
          <h2>Lista vazia</h2>
          <p>Solte os arquivos .fit na pasta data/ e clique em "Ler pasta data/" no topo.</p>
        </div>
      } @else {
        <div class="card">
          <table class="table-cards">
            <thead>
              <tr>
                <th>Data</th>
                <th>Treino</th>
                <th>Bike</th>
                <th class="num">km</th>
                <th class="num">Tempo</th>
                <th class="num">Média</th>
                <th class="num">Subida</th>
                <th class="num">FC méd</th>
                <th class="num">Pot méd</th>
                <th class="num">NP</th>
                <th class="num">IF</th>
                <th class="num">TSS</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              @for (ride of rides(); track ride.id) {
                <tr>
                  <td data-label="Data" [routerLink]="['/treinos', ride.id]">{{ ride.started_at | rideDate }}</td>
                  <td data-label="Treino" [routerLink]="['/treinos', ride.id]">{{ ride.title }}</td>
                  <td data-label="Bike">{{ ride.bike_name ?? '—' }}</td>
                  <td class="num" data-label="km">{{ ride.distance_km | num: 1 }}</td>
                  <td class="num" data-label="Tempo">{{ ride.moving_time_s | duration }}</td>
                  <td class="num" data-label="Média">{{ ride.avg_speed_kmh | num: 1 }}</td>
                  <td class="num" data-label="Subida">{{ ride.elevation_gain_m | num: 0 }}</td>
                  <td class="num" data-label="FC méd">{{ ride.avg_hr | num: 0 }}</td>
                  <td class="num" data-label="Pot méd">{{ ride.avg_power | num: 0 }}</td>
                  <td class="num" data-label="NP">{{ ride.normalized_power | num: 0 }}</td>
                  <td class="num" data-label="IF">{{ ride.intensity_factor | num: 2 }}</td>
                  <td class="num" data-label="TSS">{{ ride.tss | num: 0 }}</td>
                  <td class="num">
                    <button class="btn ghost" style="padding:4px 9px" (click)="remove(ride, $event)">Remover</button>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }
    </section>
  `,
})
export class ActivitiesComponent implements OnInit {
  private api = inject(ApiService);
  private router = inject(Router);

  rides = signal<ActivitySummary[]>([]);
  uploadMessage = signal('');

  ngOnInit(): void {
    this.load();
  }

  private load(): void {
    this.api.activities(500).subscribe((data) => this.rides.set(data));
  }

  upload(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) {
      return;
    }
    this.uploadMessage.set('Lendo ' + file.name + '…');
    this.api.upload(file).subscribe({
      next: (result) => {
        this.uploadMessage.set(
          result.status === 'importado' ? 'Treino importado.' : (result.message ?? 'Esse treino já existia.'),
        );
        input.value = '';
        this.load();
      },
      error: (err) => this.uploadMessage.set('Não deu para importar: ' + (err.error?.detail ?? 'arquivo inválido')),
    });
  }

  remove(ride: ActivitySummary, event: Event): void {
    event.stopPropagation();
    if (!confirm('Remover ' + ride.title + ' do banco? O arquivo .fit continua na pasta data/.')) {
      return;
    }
    this.api.deleteActivity(ride.id).subscribe(() => this.load());
  }

  open(id: number): void {
    this.router.navigate(['/treinos', id]);
  }
}
