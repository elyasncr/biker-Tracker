import { Component, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { ApiService } from './core/api.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    <div class="shell">
      <header class="topbar">
        <a routerLink="/" class="brand">
          <!-- Hex inline aqui e a excecao consciente a regra do theme.ts: SVG em
               template nao importa TypeScript. O simbolo e o perfil de altimetria
               com o pico em vermelho de batimento. -->
          <svg width="26" height="26" viewBox="0 0 44 44" aria-hidden="true">
            <rect width="44" height="44" rx="7" fill="#1A1A18" />
            <path d="M7,32 L14,24 L20,27 L27,14 L33,21 L37,18" fill="none" stroke="#1F7A5E"
                  stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />
            <circle cx="27" cy="14" r="3.4" fill="#B8324A" />
          </svg>
          Bike<span class="dot">·</span>Tracker
        </a>
        <nav class="nav">
          <a routerLink="/" routerLinkActive="active" [routerLinkActiveOptions]="{ exact: true }">Evolucao</a>
          <a routerLink="/treinador" routerLinkActive="active">Treinador</a>
          <a routerLink="/treinos" routerLinkActive="active">Treinos</a>
          <a routerLink="/bikes" routerLinkActive="active">Garagem</a>
          <button class="btn ghost" (click)="sync()" [disabled]="syncing()">
            {{ syncing() ? 'Lendo...' : 'Ler pasta data/' }}
          </button>
        </nav>
      </header>

      @if (message()) {
        <div class="notice" [class.error]="failed()">{{ message() }}</div>
      }

      <router-outlet />
    </div>
  `,
})
export class AppComponent {
  private api = inject(ApiService);

  syncing = signal(false);
  message = signal('');
  failed = signal(false);

  sync(): void {
    this.syncing.set(true);
    this.message.set('');
    this.api.sync().subscribe({
      next: (result) => {
        this.syncing.set(false);
        this.failed.set(result.failed > 0);
        this.message.set(
          result.imported + ' treino(s) novo(s) importado(s), ' +
            result.skipped + ' ja estavam no banco' +
            (result.failed ? ', ' + result.failed + ' com erro: ' + result.errors.join(' | ') : '.'),
        );
        if (result.imported > 0) {
          setTimeout(() => window.location.reload(), 900);
        }
      },
      error: () => {
        this.syncing.set(false);
        this.failed.set(true);
        this.message.set('Backend fora do ar. Rode: uvicorn app.main:app --reload na pasta backend/.');
      },
    });
  }
}
