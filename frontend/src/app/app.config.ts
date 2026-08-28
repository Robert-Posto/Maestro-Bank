import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideRouter, withInMemoryScrolling } from '@angular/router';

import { authInterceptor } from './core/auth.interceptor';
import { errorInterceptor } from './core/error.interceptor';
import { languageInterceptor } from './core/language.interceptor';
import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    // anchorScrolling — necesar ca navigarea cu fragment (ex. click pe o
    // notificare "document nou de semnat" din Topbar) să deruleze efectiv
    // la secțiunea vizată (vezi Topbar::openNotification), nu doar să
    // schimbe URL-ul.
    provideRouter(routes, withInMemoryScrolling({ anchorScrolling: 'enabled' })),
    provideHttpClient(withInterceptors([authInterceptor, languageInterceptor, errorInterceptor])),
  ],
};
