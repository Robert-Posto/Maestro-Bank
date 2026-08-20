import { Component, OnDestroy, ElementRef, inject, signal, viewChild } from '@angular/core';
import { Router } from '@angular/router';

import { AuthService } from '../../../services/auth.service';
import { VerificationService } from '../../../services/verification.service';
import { Icon } from '../../../shared/components/icon/icon';
import { extractErrorMessage } from '../../../shared/error-utils';

/** Pasul 2/3 din onboarding — poză buletin + selfie live, comparate de
 * verification-service (DeepFace). Camera se pornește DOAR la cerere
 * (buton explicit), niciodată automat la intrarea pe pagină. */
@Component({
  selector: 'app-verify-identity',
  standalone: true,
  imports: [Icon],
  templateUrl: './verify-identity.html',
  styleUrl: './verify-identity.css',
})
export class VerifyIdentity implements OnDestroy {
  private readonly verificationApi = inject(VerificationService);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  private readonly video = viewChild<ElementRef<HTMLVideoElement>>('video');
  private readonly canvas = viewChild<ElementRef<HTMLCanvasElement>>('canvas');
  private mediaStream: MediaStream | null = null;

  protected readonly idDocumentFile = signal<File | null>(null);
  protected readonly idDocumentPreviewUrl = signal<string | null>(null);

  protected readonly cameraActive = signal(false);
  protected readonly cameraStream = signal<MediaStream | null>(null);
  protected readonly selfieBlob = signal<Blob | null>(null);
  protected readonly selfiePreviewUrl = signal<string | null>(null);
  protected readonly cameraError = signal<string | null>(null);

  protected readonly submitting = signal(false);
  protected readonly error = signal<string | null>(null);

  ngOnDestroy(): void {
    this.stopCamera();
  }

  protected onIdDocumentSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;

    this.idDocumentFile.set(file);
    this.idDocumentPreviewUrl.set(URL.createObjectURL(file));
    this.error.set(null);
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
    const videoEl = this.video()?.nativeElement;
    const canvasEl = this.canvas()?.nativeElement;
    if (!videoEl || !canvasEl) return;

    canvasEl.width = videoEl.videoWidth;
    canvasEl.height = videoEl.videoHeight;
    const ctx = canvasEl.getContext('2d');
    ctx?.drawImage(videoEl, 0, 0);

    canvasEl.toBlob((blob) => {
      if (!blob) return;
      this.selfieBlob.set(blob);
      this.selfiePreviewUrl.set(URL.createObjectURL(blob));
      this.stopCamera();
    }, 'image/jpeg', 0.92);
  }

  protected retakePhoto(): void {
    this.selfieBlob.set(null);
    this.selfiePreviewUrl.set(null);
    this.startCamera();
  }

  private stopCamera(): void {
    this.mediaStream?.getTracks().forEach((track) => track.stop());
    this.mediaStream = null;
    this.cameraStream.set(null);
    this.cameraActive.set(false);
  }

  protected submit(): void {
    const idDocument = this.idDocumentFile();
    const selfie = this.selfieBlob();
    if (!idDocument || !selfie) {
      this.error.set('Adaugă atât poza buletinului, cât și un selfie.');
      return;
    }

    this.error.set(null);
    this.submitting.set(true);
    this.verificationApi.verifyIdentity(idDocument, selfie).subscribe({
      next: (result) => {
        this.submitting.set(false);
        if (result.verified) {
          // Ca la verify-email — reîmprospătăm signal-ul cu identity_verified=true
          // ÎNAINTE de a naviga, altfel guard-ul de la /app/* (authGuard) încă
          // vede valoarea veche și ne-ar trimite înapoi la acest pas.
          this.auth.fetchCurrentUser().subscribe({
            next: () => this.router.navigate(['/onboarding/welcome']),
            error: () => this.router.navigate(['/onboarding/welcome']),
          });
        } else {
          this.error.set(result.message);
          // Nu resetăm buletinul — doar selfie-ul, ca userul să reîncerce direct poza.
          this.selfieBlob.set(null);
          this.selfiePreviewUrl.set(null);
        }
      },
      error: (err) => {
        this.submitting.set(false);
        this.error.set(extractErrorMessage(err, 'Verificarea a eșuat. Încearcă din nou.'));
      },
    });
  }
}
