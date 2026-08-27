import { Component, ElementRef, OnDestroy, OnInit, computed, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { Router } from '@angular/router';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';

import { AuthService } from '../../services/auth.service';
import { DocumentSummary, DocumentView, DocumentsService } from '../../services/documents.service';
import { PasskeyCredential, WebauthnService } from '../../services/webauthn.service';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { ActionButton } from '../../shared/components/action-button/action-button';
import { ConfirmDialog } from '../../shared/components/confirm-dialog/confirm-dialog';
import { EmptyState } from '../../shared/components/empty-state/empty-state';
import { Icon } from '../../shared/components/icon/icon';
import { LoadingSkeleton } from '../../shared/components/loading-skeleton/loading-skeleton';
import { Modal } from '../../shared/components/modal/modal';
import { StatusBadge, BadgeTone } from '../../shared/components/status-badge/status-badge';
import { decodeJwtPayload } from '../../shared/jwt-utils';
import { ToastService } from '../../shared/components/toast/toast.service';
import { extractErrorMessage } from '../../shared/error-utils';

/** Profil & Securitate — vezi task-ul MaestroBank, secțiunea 21. */
@Component({
  selector: 'app-profile',
  standalone: true,
  imports: [
    FormsModule,
    DatePipe,
    PageHeader,
    ActionButton,
    ConfirmDialog,
    EmptyState,
    Icon,
    LoadingSkeleton,
    Modal,
    StatusBadge,
  ],
  templateUrl: './profile.html',
  styleUrl: './profile.css',
})
export class Profile implements OnInit, OnDestroy {
  private readonly auth = inject(AuthService);
  private readonly webauthn = inject(WebauthnService);
  private readonly documentsApi = inject(DocumentsService);
  private readonly sanitizer = inject(DomSanitizer);
  private readonly toast = inject(ToastService);
  private readonly router = inject(Router);

  protected readonly currentUser = this.auth.currentUser;

  // --- Poză de profil (opțională, la cererea userului) ---------------------
  protected readonly profilePictureBusy = signal(false);

  protected onProfilePictureSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    input.value = ''; // reset — re-selectarea ACELUIAȘI fișier trebuie să declanșeze din nou (change)
    if (!file) return;

    if (!file.type.startsWith('image/')) {
      this.toast.error('Alege un fișier imagine (JPEG, PNG etc.).');
      return;
    }

    this.profilePictureBusy.set(true);
    this.resizeImageToDataUri(file, 200, 200, 0.85)
      .then((dataUri) =>
        this.auth.updateProfilePicture(dataUri).subscribe({
          next: () => {
            this.profilePictureBusy.set(false);
            this.toast.success('Poza de profil a fost actualizată.');
          },
          error: (err) => {
            this.profilePictureBusy.set(false);
            this.toast.error(extractErrorMessage(err, 'Nu am putut salva poza de profil.'));
          },
        }),
      )
      .catch(() => {
        this.profilePictureBusy.set(false);
        this.toast.error('Nu am putut procesa imaginea — încearcă alt fișier.');
      });
  }

  // --- Poză de profil, LIVE cu camera — la cererea userului, la fel ca
  // pasul de verificare a identității (onboarding/verify-identity), dar
  // aici e opțional și fără comparație DeepFace: doar captură + salvare
  // directă. Reutilizăm ACELAȘI pipeline de redimensionare
  // (resizeImageToDataUri) ca la upload din fișier, ca poza să iasă
  // identică indiferent de sursă — wrapăm blob-ul capturat într-un File.
  private readonly cameraVideo = viewChild<ElementRef<HTMLVideoElement>>('profileCameraVideo');
  private readonly cameraCanvas = viewChild<ElementRef<HTMLCanvasElement>>('profileCameraCanvas');
  private mediaStream: MediaStream | null = null;

  protected readonly cameraActive = signal(false);
  protected readonly cameraStream = signal<MediaStream | null>(null);
  protected readonly cameraError = signal<string | null>(null);
  protected readonly capturedPreviewUrl = signal<string | null>(null);
  private capturedFile: File | null = null;

  ngOnDestroy(): void {
    this.stopCamera();
  }

  protected async startCamera(): Promise<void> {
    this.cameraError.set(null);
    try {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false });
      // [srcObject] din template e legat de acest signal — nu depindem de
      // timing-ul randării <video>-ului (ascuns până acum de @if).
      this.cameraStream.set(this.mediaStream);
      this.cameraActive.set(true);
    } catch {
      this.cameraError.set('Nu am putut accesa camera. Verifică permisiunile browserului.');
    }
  }

  protected capturePhoto(): void {
    const videoEl = this.cameraVideo()?.nativeElement;
    const canvasEl = this.cameraCanvas()?.nativeElement;
    if (!videoEl || !canvasEl) return;

    canvasEl.width = videoEl.videoWidth;
    canvasEl.height = videoEl.videoHeight;
    const ctx = canvasEl.getContext('2d');
    ctx?.drawImage(videoEl, 0, 0);

    canvasEl.toBlob(
      (blob) => {
        if (!blob) return;
        this.capturedFile = new File([blob], 'poza-profil.jpg', { type: 'image/jpeg' });
        this.capturedPreviewUrl.set(URL.createObjectURL(blob));
        this.stopCamera();
      },
      'image/jpeg',
      0.92,
    );
  }

  protected retakePhoto(): void {
    this.capturedFile = null;
    this.capturedPreviewUrl.set(null);
    this.startCamera();
  }

  protected cancelCameraCapture(): void {
    this.stopCamera();
    this.capturedFile = null;
    this.capturedPreviewUrl.set(null);
  }

  private stopCamera(): void {
    this.mediaStream?.getTracks().forEach((track) => track.stop());
    this.mediaStream = null;
    this.cameraStream.set(null);
    this.cameraActive.set(false);
  }

  protected saveCapturedPhoto(): void {
    const file = this.capturedFile;
    if (!file) return;

    this.profilePictureBusy.set(true);
    this.resizeImageToDataUri(file, 200, 200, 0.85)
      .then((dataUri) =>
        this.auth.updateProfilePicture(dataUri).subscribe({
          next: () => {
            this.profilePictureBusy.set(false);
            this.capturedFile = null;
            this.capturedPreviewUrl.set(null);
            this.toast.success('Poza de profil a fost actualizată.');
          },
          error: (err) => {
            this.profilePictureBusy.set(false);
            this.toast.error(extractErrorMessage(err, 'Nu am putut salva poza de profil.'));
          },
        }),
      )
      .catch(() => {
        this.profilePictureBusy.set(false);
        this.toast.error('Nu am putut procesa imaginea — încearcă din nou.');
      });
  }

  protected removeProfilePicture(): void {
    this.profilePictureBusy.set(true);
    this.auth.updateProfilePicture(null).subscribe({
      next: () => {
        this.profilePictureBusy.set(false);
        this.toast.success('Poza de profil a fost ștearsă.');
      },
      error: (err) => {
        this.profilePictureBusy.set(false);
        this.toast.error(extractErrorMessage(err, 'Nu am putut șterge poza de profil.'));
      },
    });
  }

  /** Redimensionează + comprimă imaginea ÎN BROWSER (canvas) înainte de a o
   * trimite — backend-ul o stochează direct în Mongo, fără storage extern
   * (vezi auth-service/app/models.py::ProfilePictureUpdate), deci ținem
   * poza mică intenționat (crop pătrat centrat, ~200x200, JPEG). */
  private resizeImageToDataUri(file: File, targetWidth: number, targetHeight: number, quality: number): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(reader.error);
      reader.onload = () => {
        const img = new Image();
        img.onerror = () => reject(new Error('Imagine invalidă.'));
        img.onload = () => {
          const canvas = document.createElement('canvas');
          canvas.width = targetWidth;
          canvas.height = targetHeight;
          const ctx = canvas.getContext('2d');
          if (!ctx) {
            reject(new Error('Canvas indisponibil.'));
            return;
          }
          // Crop pătrat centrat, apoi scalare la dimensiunea țintă — poza
          // nu apare distorsionată dacă originalul nu e deja pătrat.
          const side = Math.min(img.width, img.height);
          const sx = (img.width - side) / 2;
          const sy = (img.height - side) / 2;
          ctx.drawImage(img, sx, sy, side, side, 0, 0, targetWidth, targetHeight);
          resolve(canvas.toDataURL('image/jpeg', quality));
        };
        img.src = reader.result as string;
      };
      reader.readAsDataURL(file);
    });
  }

  protected readonly currentPassword = signal('');
  protected readonly newPassword = signal('');
  protected readonly confirmPassword = signal('');
  /** Ce câmpuri de parolă sunt afișate în clar (butonul cu ochi). Fiecare
   * se comută independent — vrei să verifici parola nouă fără s-o expui și
   * pe cea curentă. Pornesc toate ascunse la fiecare intrare pe pagină. */
  protected readonly passwordVisible = signal({ current: false, new: false, confirm: false });
  protected readonly changingPassword = signal(false);
  protected readonly passwordError = signal<string | null>(null);
  protected readonly passwordSuccess = signal(false);

  protected readonly sessionExpiry = computed(() => {
    const token = this.auth.getToken();
    if (!token) return null;
    const payload = decodeJwtPayload(token);
    if (!payload?.exp) return null;
    return new Date(payload.exp * 1000);
  });

  protected readonly passkeySupported = this.webauthn.isSupported();
  protected readonly passkeysLoading = signal(true);
  protected readonly passkeys = signal<PasskeyCredential[]>([]);
  protected readonly enrollingPasskey = signal(false);
  protected readonly pendingRevoke = signal<PasskeyCredential | null>(null);
  protected readonly revokingPasskey = signal(false);

  ngOnInit(): void {
    // Userul curent e deja încărcat de AppShell (o singură dată, la
    // intrarea în secțiunea /app/*) — nu-l reîncărcăm aici.
    if (this.passkeySupported) {
      this.loadPasskeys();
    } else {
      this.passkeysLoading.set(false);
    }
    this.loadDocuments();
  }

  private loadPasskeys(): void {
    this.passkeysLoading.set(true);
    this.webauthn.listCredentials().subscribe({
      next: (credentials) => {
        this.passkeys.set(credentials);
        this.passkeysLoading.set(false);
      },
      error: () => this.passkeysLoading.set(false),
    });
  }

  protected async addPasskey(): Promise<void> {
    this.enrollingPasskey.set(true);
    try {
      await this.webauthn.registerPasskey();
      this.toast.success('Passkey adăugat.');
      this.loadPasskeys();
    } catch (err) {
      if ((err as { name?: string })?.name !== 'NotAllowedError') {
        this.toast.error(extractErrorMessage(err, 'Nu am putut adăuga passkey-ul.'));
      }
    } finally {
      this.enrollingPasskey.set(false);
    }
  }

  protected confirmRevokePasskey(): void {
    const target = this.pendingRevoke();
    if (!target) return;

    this.revokingPasskey.set(true);
    this.webauthn.revokeCredential(target.id).subscribe({
      next: () => {
        this.passkeys.update((list) => list.filter((p) => p.id !== target.id));
        this.revokingPasskey.set(false);
        this.pendingRevoke.set(null);
        this.toast.success('Passkey revocat.');
      },
      error: (err) => {
        this.revokingPasskey.set(false);
        this.toast.error(extractErrorMessage(err, 'Nu am putut revoca passkey-ul.'));
      },
    });
  }

  protected togglePasswordVisibility(field: 'current' | 'new' | 'confirm'): void {
    this.passwordVisible.update((state) => ({ ...state, [field]: !state[field] }));
  }

  // --- Documente de semnat (eSign) ------------------------------------------

  protected readonly documentsLoading = signal(true);
  protected readonly documents = signal<DocumentSummary[]>([]);
  protected readonly viewTarget = signal<DocumentView | null>(null);
  protected readonly viewModalBusy = signal(false);
  protected readonly signPassword = signal('');
  protected readonly signBusy = signal(false);
  protected readonly signBiometricBusy = signal(false);

  /** La fel ca passkeyAvailable din features/cards/cards.ts — oferim
   * opțiunea biometrică DOAR dacă browserul o suportă ȘI userul are deja
   * cel puțin un passkey înrolat, nu doar suport teoretic. */
  protected readonly signPasskeyAvailable = computed(() => this.passkeySupported && this.passkeys().length > 0);

  /** <embed src> e context RESOURCE_URL pentru Angular — un data: URI
   * "brut" (netratat explicit ca sigur) e respins de sanitizer înainte să
   * ajungă în DOM, ceea ce lăsa tot conținutul modalului needarat (nu doar
   * PDF-ul). bypassSecurityTrustResourceUrl e sigur aici — valoarea vine
   * STRICT din propriul nostru backend (support-service), niciodată din
   * input direct al userului. */
  protected readonly documentViewerUrl = computed<SafeResourceUrl | null>(() => {
    const doc = this.viewTarget();
    return doc ? this.sanitizer.bypassSecurityTrustResourceUrl(doc.pdf_data) : null;
  });

  private loadDocuments(): void {
    this.documentsLoading.set(true);
    this.documentsApi.listMyDocuments().subscribe({
      next: (documents) => {
        this.documents.set(documents);
        this.documentsLoading.set(false);
      },
      error: () => this.documentsLoading.set(false),
    });
  }

  protected documentStatusTone(status: DocumentSummary['status']): BadgeTone {
    if (status === 'signed') return 'success';
    if (status === 'cancelled') return 'neutral';
    return 'warning';
  }

  protected documentStatusLabel(status: DocumentSummary['status']): string {
    if (status === 'signed') return 'Semnat';
    if (status === 'cancelled') return 'Anulat';
    return 'În așteptare';
  }

  protected openDocument(doc: DocumentSummary): void {
    this.viewModalBusy.set(true);
    this.signPassword.set('');
    this.documentsApi.getDocument(doc.id).subscribe({
      next: (full) => {
        this.viewTarget.set(full);
        this.viewModalBusy.set(false);
      },
      error: (err) => {
        this.viewModalBusy.set(false);
        this.toast.error(extractErrorMessage(err, 'Nu am putut deschide documentul.'));
      },
    });
  }

  protected closeDocumentModal(): void {
    if (this.signBusy() || this.signBiometricBusy()) return;
    this.viewTarget.set(null);
    this.signPassword.set('');
  }

  private applySignSuccess(clearBusy: () => void): void {
    const target = this.viewTarget();
    clearBusy();
    if (target) {
      this.documents.update((list) =>
        list.map((doc) => (doc.id === target.id ? { ...doc, status: 'signed', signed_at: new Date().toISOString() } : doc)),
      );
    }
    this.viewTarget.set(null);
    this.signPassword.set('');
    this.toast.success('Documentul a fost semnat.');
  }

  protected submitSignWithPassword(): void {
    const target = this.viewTarget();
    if (!target || !this.signPassword()) {
      this.toast.error('Introdu parola contului.');
      return;
    }

    this.signBusy.set(true);
    this.documentsApi.signDocument(target.id, { password: this.signPassword() }).subscribe({
      next: () => this.applySignSuccess(() => this.signBusy.set(false)),
      error: (err) => {
        this.signBusy.set(false);
        this.toast.error(extractErrorMessage(err, 'Parolă incorectă.'));
      },
    });
  }

  protected async submitSignWithBiometrics(): Promise<void> {
    const target = this.viewTarget();
    if (!target) return;

    this.signBiometricBusy.set(true);
    try {
      const proof = await this.webauthn.getStepUpAssertion('document_sign', target.id);
      this.documentsApi.signDocument(target.id, proof).subscribe({
        next: () => this.applySignSuccess(() => this.signBiometricBusy.set(false)),
        error: (err) => {
          this.signBiometricBusy.set(false);
          this.toast.error(extractErrorMessage(err, 'Confirmarea biometrică a eșuat — poți folosi parola.'));
        },
      });
    } catch (err) {
      this.signBiometricBusy.set(false);
      // Userul a anulat prompt-ul biometric (NotAllowedError) — nu e o
      // eroare de afișat, câmpul parolei rămâne oricum disponibil mai jos.
      if ((err as { name?: string })?.name !== 'NotAllowedError') {
        this.toast.error('Confirmarea biometrică nu a funcționat — poți folosi parola.');
      }
    }
  }

  protected changePassword(): void {
    this.passwordError.set(null);
    this.passwordSuccess.set(false);

    if (!this.currentPassword() || !this.newPassword() || !this.confirmPassword()) {
      this.passwordError.set('Completează toate câmpurile.');
      return;
    }
    if (this.newPassword() !== this.confirmPassword()) {
      this.passwordError.set('Parola nouă și confirmarea nu coincid.');
      return;
    }

    this.changingPassword.set(true);
    this.auth.changePassword({ current_password: this.currentPassword(), new_password: this.newPassword() }).subscribe({
      next: () => {
        this.changingPassword.set(false);
        this.passwordSuccess.set(true);
        this.currentPassword.set('');
        this.newPassword.set('');
        this.confirmPassword.set('');
        this.toast.success('Parola a fost schimbată cu succes.');
      },
      error: (err) => {
        this.changingPassword.set(false);
        this.passwordError.set(extractErrorMessage(err, 'Schimbarea parolei a eșuat.'));
      },
    });
  }

  protected logout(): void {
    this.auth.logout();
    this.router.navigate(['/login']);
  }
}
