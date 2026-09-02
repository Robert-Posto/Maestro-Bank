import { TranslationEntry } from './index';

/** Sidebar + topbar — navigarea principală, vizibilă pe orice pagină din
 * /app/*, deci prioritate maximă de tradus (vezi planul fazei). */
export const NAV_I18N: Record<string, TranslationEntry> = {
  'nav.group.banking': { ro: 'Bancar', en: 'Banking' },
  'nav.group.planning': { ro: 'Planificare', en: 'Planning' },
  'nav.group.assistants': { ro: 'Asistenți AI', en: 'AI Assistants' },

  'nav.overview': { ro: 'Overview', en: 'Overview' },
  'nav.accounts': { ro: 'Conturi', en: 'Accounts' },
  'nav.cards': { ro: 'Carduri', en: 'Cards' },
  'nav.transactions': { ro: 'Tranzacții', en: 'Transactions' },
  'nav.transfers': { ro: 'Plăți & Transferuri', en: 'Payments & Transfers' },
  'nav.exchange': { ro: 'Schimb valutar', en: 'Currency exchange' },
  'nav.investments': { ro: 'Investiții', en: 'Investments' },
  'nav.loans': { ro: 'Credite', en: 'Loans' },
  'nav.budgets': { ro: 'Bugete', en: 'Budgets' },
  'nav.forecast': { ro: 'Spending & Forecast', en: 'Spending & Forecast' },
  'nav.copilot': { ro: 'MaestroAgent', en: 'MaestroAgent' },
  'nav.support': { ro: 'Support', en: 'Support' },
  'nav.assistant': { ro: 'Asistent', en: 'Assistant' },

  'topbar.search': { ro: 'Caută tranzacții, comercianți, categorii...', en: 'Search transactions, merchants, categories...' },
  'topbar.newTransaction': { ro: 'Tranzacție nouă', en: 'New transaction' },
  'topbar.noNotificationsYet': { ro: 'Nicio notificare încă.', en: 'No notifications yet.' },
  'topbar.deleteNotification': { ro: 'Șterge notificarea', en: 'Delete notification' },
  'topbar.switchToLight': { ro: 'Comută la tema deschisă', en: 'Switch to light theme' },
  'topbar.switchToDark': { ro: 'Comută la tema închisă', en: 'Switch to dark theme' },
  'topbar.notifications': { ro: 'Notificări', en: 'Notifications' },
  'topbar.markAllRead': { ro: 'Marchează toate ca citite', en: 'Mark all as read' },
  'topbar.noNotifications': { ro: 'Nicio notificare', en: 'No notifications' },
  'topbar.profile': { ro: 'Profil & Securitate', en: 'Profile & Security' },
  'topbar.logout': { ro: 'Ieși din cont', en: 'Log out' },
  'topbar.theme': { ro: 'Schimbă tema', en: 'Switch theme' },
  'topbar.language': { ro: 'Limbă', en: 'Language' },

  'admin.brand.name': { ro: 'Personal', en: 'Staff' },
  'admin.brand.subtitle': { ro: 'Zonă restricționată — vizibilă doar personalului', en: 'Restricted area — staff only' },
  'admin.nav.holds': { ro: 'Rețineri', en: 'Holds' },
  'admin.nav.blocklist': { ro: 'Blocklist', en: 'Blocklist' },
  'admin.nav.documents': { ro: 'Documente', en: 'Documents' },
  'admin.nav.loanApplications': { ro: 'Cereri credit', en: 'Loan applications' },
};
