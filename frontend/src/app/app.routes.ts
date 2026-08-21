import { Routes } from '@angular/router';

import { authGuard, guestGuard } from './core/auth.guard';
import { staffGuard } from './core/staff.guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'login' },
  {
    path: 'login',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/auth/login/login').then((m) => m.Login),
  },
  {
    path: 'register',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/auth/register/register').then((m) => m.Register),
  },
  {
    path: 'app',
    canActivate: [authGuard],
    loadComponent: () => import('./shared/components/app-shell/app-shell').then((m) => m.AppShell),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'overview' },
      {
        path: 'overview',
        loadComponent: () => import('./features/overview/overview').then((m) => m.Overview),
      },
      {
        path: 'accounts',
        loadComponent: () => import('./features/accounts/accounts').then((m) => m.Accounts),
      },
      {
        path: 'cards',
        loadComponent: () => import('./features/cards/cards').then((m) => m.Cards),
      },
      {
        path: 'transactions',
        loadComponent: () => import('./features/transactions/transactions').then((m) => m.Transactions),
      },
      {
        path: 'transfers',
        loadComponent: () => import('./features/transfers/transfers').then((m) => m.Transfers),
      },
      {
        path: 'exchange',
        loadComponent: () => import('./features/exchange/exchange').then((m) => m.Exchange),
      },
      {
        path: 'budgets',
        loadComponent: () => import('./features/budgets/budgets').then((m) => m.Budgets),
      },
      {
        path: 'spending-forecast',
        loadComponent: () =>
          import('./features/spending-forecast/spending-forecast').then((m) => m.SpendingForecast),
      },
      {
        path: 'support',
        loadComponent: () => import('./features/support/support').then((m) => m.Support),
      },
      {
        path: 'copilot',
        loadComponent: () => import('./features/copilot/copilot').then((m) => m.Copilot),
      },
      {
        path: 'profile',
        loadComponent: () => import('./features/profile/profile').then((m) => m.Profile),
      },
      {
        path: 'staff-holds',
        canActivate: [staffGuard],
        loadComponent: () => import('./features/staff-holds/staff-holds').then((m) => m.StaffHolds),
      },
    ],
  },
  { path: '**', redirectTo: 'login' },
];
