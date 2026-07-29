import { Pipe, PipeTransform } from '@angular/core';

/** 4820 -> "1h20"  |  2700 -> "45min" */
@Pipe({ name: 'duration', standalone: true })
export class DurationPipe implements PipeTransform {
  transform(seconds: number | null | undefined): string {
    if (seconds === null || seconds === undefined) {
      return '--';
    }
    const total = Math.round(seconds);
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    if (hours === 0) {
      return minutes + 'min';
    }
    return hours + 'h' + String(minutes).padStart(2, '0');
  }
}

/** Duracao curta para eixos: 300 -> "5min", 45 -> "45s" */
@Pipe({ name: 'shortDuration', standalone: true })
export class ShortDurationPipe implements PipeTransform {
  transform(seconds: number): string {
    if (seconds < 60) {
      return seconds + 's';
    }
    if (seconds < 3600) {
      return seconds / 60 + 'min';
    }
    return seconds / 3600 + 'h';
  }
}

/** Numero com casas fixas, ou "--" quando nao existe. */
@Pipe({ name: 'num', standalone: true })
export class NumPipe implements PipeTransform {
  transform(value: number | null | undefined, digits = 0): string {
    if (value === null || value === undefined) {
      return '--';
    }
    return value.toLocaleString('pt-BR', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  }
}

/** 2026-06-19T06:30:00 -> "19 jun, 06:30" */
@Pipe({ name: 'rideDate', standalone: true })
export class RideDatePipe implements PipeTransform {
  private months = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];

  transform(value: string | null | undefined, withTime = true): string {
    if (!value) {
      return '--';
    }
    const d = new Date(value);
    const base = d.getDate() + ' ' + this.months[d.getMonth()];
    if (!withTime) {
      return base + ' ' + d.getFullYear();
    }
    return base + ', ' + String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
  }
}
