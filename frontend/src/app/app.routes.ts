import { Routes } from '@angular/router';

import { staffGuard } from './core/staff.guard';
import { authGuard, guestGuard, onboardingAuthGuard, onboardingIdentityGuard } from './core/auth.guard';

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
    path: 'onboarding',
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'verify-email' },
      {
        path: 'verify-email',
        canActivate: [onboardingAuthGuard],
        loadComponent: () => import('./features/onboarding/verify-email/verify-email').then((m) => m.VerifyEmail),
      },
      {
        path: 'verify-identity',
        canActivate: [onboardingIdentityGuard],
        loadComponent: () =>
          import('./features/onboarding/verify-identity/verify-identity').then((m) => m.VerifyIdentity),
      },
      {
        path: 'welcome',
        canActivate: [onboardingAuthGuard],
        loadComponent: () => import('./features/onboarding/welcome/welcome').then((m) => m.Welcome),
      },
    ],
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
        // Pagina deschisă de link-ul de "Cerere de plată" (vezi Transfers,
        // tab "Solicită plată") — orice user autentificat o poate deschide și
        // plăti, nu doar cel care a creat cererea (authGuard de pe 'app'
        // e suficient, nu mai adăugăm un guard separat aici).
        path: 'pay/:id',
        loadComponent: () => import('./features/pay-request/pay-request').then((m) => m.PayRequest),
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
    ],
  },
  {
    // Zonă separată, deliberat NU sub /app — vezi AdminShell. Un customer
    // normal nu ajunge niciodată aici (staffGuard), dar și vizual/structural
    // e altă rută, nu doar o pagină ascunsă în sidebar-ul obișnuit.
    path: 'admin',
    canActivate: [staffGuard],
    loadComponent: () => import('./shared/components/admin-shell/admin-shell').then((m) => m.AdminShell),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'holds' },
      {
        path: 'holds',
        loadComponent: () => import('./features/staff-holds/staff-holds').then((m) => m.StaffHolds),
      },
      {
        path: 'customers/:userId',
        loadComponent: () => import('./features/staff-customer/staff-customer').then((m) => m.StaffCustomer),
      },
    ],
  },
  { path: '**', redirectTo: 'login' },
];
