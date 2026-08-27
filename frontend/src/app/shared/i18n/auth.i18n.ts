import { TranslationEntry } from './index';

/** Login, Register, Onboarding (verify-email, verify-identity, welcome) —
 * primul contact cu aplicația, deci prioritate maximă (vezi planul fazei).
 * Toate cele 5 pagini refolosesc exact aceeași structură auth-brand/
 * auth-visual — brandul e o singură cheie, restul e specific per pagină. */
export const AUTH_I18N: Record<string, TranslationEntry> = {
  'auth.brand.name': { ro: 'MaestroBank', en: 'MaestroBank' },
  'auth.brand.tagline': { ro: 'maestrul tău în banking', en: 'your master of banking' },

  // --- Login -----------------------------------------------------------
  'auth.login.eyebrow': { ro: 'Banking simplificat', en: 'Banking made simple' },
  'auth.login.title': { ro: 'Finanțele tale, într-un singur loc.', en: 'Your finances, all in one place.' },
  'auth.login.text': {
    ro: 'Conturi, plăți și informații utile, într-o experiență sigură și ușor de folosit.',
    en: 'Accounts, payments and useful insights, in a secure and easy-to-use experience.',
  },
  'auth.login.security': { ro: 'Conexiune securizată și date protejate', en: 'Secure connection and protected data' },
  'auth.login.title2': { ro: 'Autentificare', en: 'Sign in' },
  'auth.login.subtitle': { ro: 'Accesează contul tău MaestroBank.', en: 'Access your MaestroBank account.' },
  'auth.login.sessionExpired': {
    ro: 'Sesiunea a expirat. Te rugăm să te autentifici din nou.',
    en: 'Your session has expired. Please sign in again.',
  },
  'auth.login.emailPlaceholder': { ro: 'nume@exemplu.com', en: 'name@example.com' },
  'auth.login.submitting': { ro: 'Se autentifică...', en: 'Signing in...' },
  'auth.login.submit': { ro: 'Autentifică-te', en: 'Sign in' },
  'auth.login.or': { ro: 'sau', en: 'or' },
  'auth.login.passkeyBusy': { ro: 'Se confirmă...', en: 'Confirming...' },
  'auth.login.passkey': { ro: 'Autentificare cu passkey', en: 'Sign in with a passkey' },
  'auth.login.noAccount': { ro: 'Nu ai cont?', en: "Don't have an account?" },
  'auth.login.createOne': { ro: 'Creează unul', en: 'Create one' },
  'auth.login.fillBoth': { ro: 'Completează email-ul și parola.', en: 'Fill in both your email and password.' },
  'auth.login.failed': {
    ro: 'Autentificare eșuată. Verifică email-ul și parola.',
    en: 'Sign-in failed. Check your email and password.',
  },
  'auth.login.fillEmailForPasskey': {
    ro: 'Completează email-ul, apoi folosește passkey-ul.',
    en: 'Fill in your email, then use your passkey.',
  },
  'auth.login.passkeyFailed': {
    ro: 'Autentificarea cu passkey a eșuat. Poți folosi parola.',
    en: 'Passkey sign-in failed. You can use your password instead.',
  },

  // --- Register ----------------------------------------------------------
  'auth.register.eyebrow': { ro: 'Începe simplu', en: 'Get started' },
  'auth.register.title': { ro: 'Un cont construit în jurul tău.', en: 'An account built around you.' },
  'auth.register.text': {
    ro: 'Ai acces rapid la sold, card virtual și instrumentele de care ai nevoie zi de zi.',
    en: 'Quick access to your balance, a virtual card and the tools you need every day.',
  },
  'auth.register.security': { ro: 'Înregistrare rapidă și protejată', en: 'Fast and protected sign-up' },
  'auth.register.back': { ro: 'Înapoi la autentificare', en: 'Back to sign in' },
  'auth.register.title2': { ro: 'Creează cont', en: 'Create an account' },
  'auth.register.subtitle': {
    ro: 'Contul RON, IBAN-ul demo și cardul virtual se creează automat. Urmează 2 pași rapizi de verificare — email și identitate.',
    en: 'Your RON account, demo IBAN and virtual card are created automatically. Two quick verification steps follow — email and identity.',
  },
  'auth.register.firstName': { ro: 'Prenume', en: 'First name' },
  'auth.register.lastName': { ro: 'Nume', en: 'Last name' },
  'auth.register.phone': { ro: 'Telefon', en: 'Phone' },
  'auth.register.phoneHint': {
    ro: 'Folosit doar pentru contact — necesar acum, verificarea prin SMS vine într-o etapă viitoare.',
    en: 'Used for contact only — required for now, SMS verification is coming in a future update.',
  },
  'auth.register.phonePlaceholder': { ro: '+40 7xx xxx xxx', en: '+40 7xx xxx xxx' },
  'auth.register.passwordHint': {
    ro: 'Minimum 8 caractere, cel puțin o literă și o cifră.',
    en: 'At least 8 characters, including one letter and one digit.',
  },
  'auth.register.success': { ro: 'Cont creat. Te autentificăm automat...', en: 'Account created. Signing you in...' },
  'auth.register.submitting': { ro: 'Se creează...', en: 'Creating...' },
  'auth.register.submit': { ro: 'Creează cont', en: 'Create account' },
  'auth.register.haveAccount': { ro: 'Ai deja cont?', en: 'Already have an account?' },
  'auth.register.signIn': { ro: 'Autentifică-te', en: 'Sign in' },
  'auth.register.fillAllFields': { ro: 'Completează toate câmpurile.', en: 'Fill in all fields.' },
  'auth.register.failed': { ro: 'Înregistrarea a eșuat.', en: 'Registration failed.' },

  // --- Onboarding: verify email -------------------------------------------
  'auth.verifyEmail.eyebrow': { ro: 'Pasul 1 din 3', en: 'Step 1 of 3' },
  'auth.verifyEmail.title': { ro: 'Confirmă-ți adresa de email.', en: 'Confirm your email address.' },
  'auth.verifyEmail.text': {
    ro: 'Un cont verificat înseamnă un cont mai sigur — un singur cod, primit pe mail, e tot ce ne trebuie.',
    en: 'A verified account is a safer account — a single code, sent to your inbox, is all we need.',
  },
  'auth.verifyEmail.security': { ro: 'Conexiune securizată și date protejate', en: 'Secure connection and protected data' },
  'auth.verifyEmail.exit': { ro: 'Renunță și ieși', en: 'Cancel and exit' },
  'auth.verifyEmail.title2': { ro: 'Verifică-ți emailul', en: 'Verify your email' },
  'auth.verifyEmail.subtitle': { ro: 'Am trimis un cod de 6 cifre către', en: 'We sent a 6-digit code to' },
  'auth.verifyEmail.codeLabel': { ro: 'Cod de verificare', en: 'Verification code' },
  'auth.verifyEmail.resent': { ro: 'Cod nou trimis.', en: 'New code sent.' },
  'auth.verifyEmail.verifying': { ro: 'Se verifică...', en: 'Verifying...' },
  'auth.verifyEmail.confirm': { ro: 'Confirmă', en: 'Confirm' },
  'auth.verifyEmail.noCode': { ro: "N-ai primit codul?", en: "Didn't get the code?" },
  'auth.verifyEmail.resending': { ro: 'Se retrimite...', en: 'Resending...' },
  'auth.verifyEmail.resend': { ro: 'Retrimite codul', en: 'Resend code' },
  'auth.verifyEmail.codeLength': { ro: 'Codul are 6 cifre.', en: 'The code is 6 digits long.' },
  'auth.verifyEmail.incorrectCode': { ro: 'Cod incorect. Încearcă din nou.', en: 'Incorrect code. Try again.' },
  'auth.verifyEmail.resendFailed': { ro: 'Nu am putut retrimite codul.', en: "We couldn't resend the code." },

  // --- Onboarding: verify identity -----------------------------------------
  'auth.verifyIdentity.eyebrow': { ro: 'Pasul 2 din 3', en: 'Step 2 of 3' },
  'auth.verifyIdentity.title': { ro: 'Confirmă că ești chiar tu.', en: "Confirm it's really you." },
  'auth.verifyIdentity.text': {
    ro: 'Comparăm poza buletinului cu un selfie live — verificare reală, nu doar bifată la formular.',
    en: 'We compare your ID photo with a live selfie — real verification, not just a checkbox.',
  },
  'auth.verifyIdentity.security': {
    ro: 'Imaginile NU sunt salvate — doar rezultatul comparării',
    en: 'Images are NOT saved — only the comparison result',
  },
  'auth.verifyIdentity.back': { ro: 'Înapoi', en: 'Back' },
  'auth.verifyIdentity.title2': { ro: 'Verifică-ți identitatea', en: 'Verify your identity' },
  'auth.verifyIdentity.subtitle': {
    ro: 'Încarcă buletinul, apoi fă un selfie — le comparăm automat.',
    en: 'Upload your ID, then take a selfie — we compare them automatically.',
  },
  'auth.verifyIdentity.idLabel': { ro: 'Buletin', en: 'ID card' },
  'auth.verifyIdentity.changePhoto': { ro: 'Schimbă poza', en: 'Change photo' },
  'auth.verifyIdentity.uploadId': { ro: 'Încarcă poza buletinului', en: 'Upload your ID photo' },
  'auth.verifyIdentity.selfieLabel': { ro: 'Selfie', en: 'Selfie' },
  'auth.verifyIdentity.retake': { ro: 'Refă poza', en: 'Retake photo' },
  'auth.verifyIdentity.takePhoto': { ro: 'Fă poza', en: 'Take photo' },
  'auth.verifyIdentity.startCamera': { ro: 'Pornește camera', en: 'Start camera' },
  'auth.verifyIdentity.verifying': { ro: 'Se verifică...', en: 'Verifying...' },
  'auth.verifyIdentity.confirm': { ro: 'Confirmă identitatea', en: 'Confirm identity' },
  'auth.verifyIdentity.cameraDenied': {
    ro: 'Nu am putut accesa camera. Verifică permisiunile browserului.',
    en: "We couldn't access the camera. Check your browser permissions.",
  },
  'auth.verifyIdentity.missingFiles': {
    ro: 'Adaugă atât poza buletinului, cât și un selfie.',
    en: 'Add both your ID photo and a selfie.',
  },
  'auth.verifyIdentity.failed': { ro: 'Verificarea a eșuat. Încearcă din nou.', en: 'Verification failed. Try again.' },

  // --- Onboarding: welcome --------------------------------------------------
  'auth.welcome.eyebrow': { ro: 'Pasul 3 din 3', en: 'Step 3 of 3' },
  'auth.welcome.title': { ro: 'Bine ai venit în MaestroBank!', en: 'Welcome to MaestroBank!' },
  'auth.welcome.text': {
    ro: 'Contul tău e verificat și gata de folosit — chiar de la primul transfer.',
    en: 'Your account is verified and ready to use — right from your first transfer.',
  },
  'auth.welcome.security': { ro: 'Cont complet verificat', en: 'Fully verified account' },
  'auth.welcome.ready': { ro: 'Gata', en: 'All set' },
  'auth.welcome.subtitle': {
    ro: 'Emailul și identitatea ta sunt confirmate. Contul tău e complet activ.',
    en: 'Your email and identity are confirmed. Your account is fully active.',
  },
  'auth.welcome.bonusLabel': { ro: 'Bonus de bun venit', en: 'Welcome bonus' },
  'auth.welcome.currentBalance': { ro: 'Sold curent:', en: 'Current balance:' },
  'auth.welcome.preparing': { ro: 'Se pregătește contul...', en: 'Preparing your account...' },
  'auth.welcome.enter': { ro: 'Intră în cont', en: 'Enter your account' },
};
