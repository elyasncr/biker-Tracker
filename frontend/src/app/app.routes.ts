import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', loadComponent: () => import('./pages/dashboard.component').then((m) => m.DashboardComponent) },
  { path: 'treinador', loadComponent: () => import('./pages/coach.component').then((m) => m.CoachComponent) },
  { path: 'treinos', loadComponent: () => import('./pages/activities.component').then((m) => m.ActivitiesComponent) },
  { path: 'treinos/:id', loadComponent: () => import('./pages/activity-detail.component').then((m) => m.ActivityDetailComponent) },
  { path: 'bikes', loadComponent: () => import('./pages/bikes.component').then((m) => m.BikesComponent) },
  { path: '**', redirectTo: '' },
];
