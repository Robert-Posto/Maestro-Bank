import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { AssistantService } from '../../services/assistant.service';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { ActionButton } from '../../shared/components/action-button/action-button';
import { Icon } from '../../shared/components/icon/icon';
import { ToastService } from '../../shared/components/toast/toast.service';
import { extractErrorMessage } from '../../shared/error-utils';

const EXAMPLE_QUESTIONS = [
  'Îmi permit o vacanță de 2.000 lei luna asta?',
  'Cardul meu e activ?',
  'Cât mai am de plătit la creditul meu?',
  'Câte puncte am acumulat?',
];

/**
 * Un singur loc unde userul întreabă orice — orchestrator SUBȚIRE (vezi
 * AssistantService), NU un al treilea agent. Clasifică întrebarea O
 * SINGURĂ dată (determinist, pe server) și trimite userul direct la
 * pagina potrivită (MaestroAgent sau Support), cu mesajul deja "trimis"
 * acolo — userul nu-l retastează. MaestroAgent și Support rămân exact
 * cum erau, complet neatinse — pagina asta doar alege între ele.
 */
@Component({
  selector: 'app-assistant',
  standalone: true,
  imports: [FormsModule, PageHeader, ActionButton, Icon],
  templateUrl: './assistant.html',
  styleUrl: './assistant.css',
})
export class Assistant {
  private readonly assistantApi = inject(AssistantService);
  private readonly router = inject(Router);
  private readonly toast = inject(ToastService);

  protected readonly exampleQuestions = EXAMPLE_QUESTIONS;
  protected readonly question = signal('');
  protected readonly routing = signal(false);

  protected ask(text?: string): void {
    const message = (text ?? this.question()).trim();
    if (!message || this.routing()) return;

    this.routing.set(true);
    this.assistantApi.classify(message).subscribe({
      next: (result) => {
        this.routing.set(false);
        this.router.navigate([result.route], { queryParams: { q: message } });
      },
      error: (err) => {
        this.routing.set(false);
        this.toast.error(extractErrorMessage(err, 'Nu am putut ruta întrebarea.'));
      },
    });
  }
}
