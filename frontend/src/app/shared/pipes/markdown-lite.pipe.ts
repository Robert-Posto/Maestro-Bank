import { Pipe, PipeTransform, inject } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';

/**
 * Markdown "lite" -> HTML — DOAR pentru textul generat de agentul AI
 * (MaestroAssistent, vezi features/copilot). GPT scrie de obicei în
 * Markdown (**bold**, liste cu "- "), dar text-ul brut arăta urât ca
 * text simplu (liniuțe/asteriscuri literale) — vezi feedback userul.
 *
 * Suportă STRICT ce generează de obicei modelul în răspunsuri scurte:
 * **bold**, liste cu marcatori ("- "/"* "), liste numerotate ("1. "),
 * paragrafe separate de linie goală. NU e un parser Markdown complet
 * (fără linkuri/cod/tabele) — intenționat minimal, pentru un singur scop.
 *
 * SIGURANȚĂ: textul e HTML-escaped ÎNAINTE de orice transformare — orice
 * tag literal din răspunsul modelului apare ca text simplu, nu se
 * execută. Doar tag-urile construite AICI (strong/ul/ol/li/p/br) ajung
 * în DOM, deci `bypassSecurityTrustHtml` e sigur de folosit.
 */
@Pipe({ name: 'markdownLite', standalone: true })
export class MarkdownLitePipe implements PipeTransform {
  private readonly sanitizer = inject(DomSanitizer);

  transform(value: string | null | undefined): SafeHtml {
    if (!value) return '';
    const html = this.toHtml(this.escapeHtml(value));
    return this.sanitizer.bypassSecurityTrustHtml(html);
  }

  private escapeHtml(text: string): string {
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  private toHtml(escaped: string): string {
    return escaped
      .split(/\n{2,}/)
      .map((block) => this.blockToHtml(block.trim()))
      .filter(Boolean)
      .join('');
  }

  private blockToHtml(block: string): string {
    if (!block) return '';
    const lines = block
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);

    if (lines.every((line) => /^[-*]\s+/.test(line))) {
      const items = lines.map((line) => `<li>${this.inline(line.replace(/^[-*]\s+/, ''))}</li>`).join('');
      return `<ul>${items}</ul>`;
    }

    if (lines.every((line) => /^\d+[.)]\s+/.test(line))) {
      const items = lines.map((line) => `<li>${this.inline(line.replace(/^\d+[.)]\s+/, ''))}</li>`).join('');
      return `<ol>${items}</ol>`;
    }

    return `<p>${lines.map((line) => this.inline(line)).join('<br>')}</p>`;
  }

  private inline(text: string): string {
    return text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  }
}
