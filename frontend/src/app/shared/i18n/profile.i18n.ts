import { TranslationEntry } from './index';

export const PROFILE_I18N: Record<string, TranslationEntry> = {
  'profile.title': { ro: 'Profil & Securitate', en: 'Profile & Security' },
  'profile.subtitle': { ro: 'Datele contului tău și opțiunile de securitate.', en: 'Your account details and security options.' },
  'profile.logout': { ro: 'Ieși din cont', en: 'Log out' },

  'profile.pictureAlt': { ro: 'Poză de profil', en: 'Profile picture' },
  'profile.capturedPreviewAlt': { ro: 'Previzualizare poză capturată', en: 'Captured photo preview' },
  'profile.changePicture': { ro: 'Schimbă poza', en: 'Change picture' },
  'profile.takePhoto': { ro: 'Fă poza cu camera', en: 'Take a photo with the camera' },
  'profile.removePicture': { ro: 'Șterge poza', en: 'Remove picture' },
  'profile.retakePhoto': { ro: 'Refă poza', en: 'Retake photo' },
  'profile.shutterAria': { ro: 'Fă poza', en: 'Take photo' },
  'profile.discard': { ro: 'Renunță', en: 'Discard' },

  'profile.identity': { ro: 'Identitate', en: 'Identity' },
  'profile.verified': { ro: 'Verificată', en: 'Verified' },
  'profile.pending': { ro: 'În așteptare', en: 'Pending' },
  'profile.identityVerifiedDesc': { ro: 'Contul tău e verificat complet.', en: 'Your account is fully verified.' },
  'profile.identityPendingDesc': { ro: 'Verificarea nu e încă finalizată.', en: 'Verification is not yet complete.' },

  'profile.passkeys': { ro: 'Passkeys', en: 'Passkeys' },
  'profile.passkeysActiveDesc': { ro: 'Autentificare fără parolă, activă.', en: 'Passwordless sign-in, active.' },
  'profile.passkeysNoneDesc': { ro: 'Niciunul înregistrat încă.', en: 'None registered yet.' },

  'profile.documents': { ro: 'Documente', en: 'Documents' },
  'profile.documentsSectionTitle': { ro: 'Documente de semnat', en: 'Documents to sign' },
  'profile.documentsPanelDesc': {
    ro: 'Documente trimise de personalul băncii, de semnat direct de aici.',
    en: 'Documents sent by bank staff, to sign directly from here.',
  },
  'profile.documentsPendingDesc': { ro: 'În așteptarea semnăturii tale.', en: 'Awaiting your signature.' },
  'profile.documentsNoneDesc': { ro: 'Nimic de semnat momentan.', en: 'Nothing to sign right now.' },

  'profile.session': { ro: 'Sesiune', en: 'Session' },
  'profile.expires': { ro: 'Expiră', en: 'Expires' },
  'profile.authenticated': { ro: 'Autentificat.', en: 'Authenticated.' },

  'profile.security': { ro: 'Securitate', en: 'Security' },

  'profile.passkeysDesc': {
    ro: 'Autentifică-te și confirmă acțiuni sensibile (ex. vezi datele unui card) cu Face ID, Touch ID sau Windows Hello, în loc de parolă.',
    en: 'Sign in and confirm sensitive actions (e.g. viewing card details) with Face ID, Touch ID, or Windows Hello, instead of a password.',
  },
  'profile.passkeysUnsupported': {
    ro: 'Browserul tău nu suportă passkey-uri — poți folosi în continuare parola.',
    en: 'Your browser does not support passkeys — you can still use your password.',
  },
  'profile.noPasskeysTitle': { ro: 'Niciun passkey înregistrat', en: 'No passkeys registered' },
  'profile.noPasskeysDesc': {
    ro: 'Adaugă unul pentru autentificare rapidă cu Face ID, Touch ID sau Windows Hello, fără parolă.',
    en: 'Add one for fast sign-in with Face ID, Touch ID, or Windows Hello, without a password.',
  },
  'profile.passkeySingular': { ro: 'Passkey', en: 'Passkey' },
  'profile.addedOn': { ro: 'Adăugat', en: 'Added' },
  'profile.lastUsed': { ro: 'folosit ultima dată', en: 'last used' },
  'profile.revokePasskeyAria': { ro: 'Revocă passkey-ul', en: 'Revoke passkey' },
  'profile.addPasskeyBtn': { ro: 'Adaugă un passkey', en: 'Add a passkey' },

  'profile.changePasswordTitle': { ro: 'Schimbă parola', en: 'Change password' },
  'profile.currentPassword': { ro: 'Parola curentă', en: 'Current password' },
  'profile.newPassword': { ro: 'Parolă nouă', en: 'New password' },
  'profile.confirmNewPassword': { ro: 'Confirmă parola nouă', en: 'Confirm new password' },
  'profile.fillAllFields': { ro: 'Completează toate câmpurile.', en: 'Fill in all the fields.' },
  'profile.passwordMismatch': { ro: 'Parola nouă și confirmarea nu coincid.', en: 'The new password and confirmation do not match.' },
  'profile.changePasswordError': { ro: 'Schimbarea parolei a eșuat.', en: 'Changing the password failed.' },
  'profile.passwordChangedToast': { ro: 'Parola a fost schimbată cu succes.', en: 'Password changed successfully.' },
  'profile.passwordUpdatedMessage': { ro: 'Parola a fost actualizată.', en: 'Password updated.' },
  'profile.updatePasswordBtn': { ro: 'Actualizează parola', en: 'Update password' },

  'profile.noDocumentsTitle': { ro: 'Niciun document de semnat', en: 'No documents to sign' },
  'profile.noDocumentsDesc': {
    ro: 'Când personalul îți trimite un document, va apărea aici.',
    en: 'When staff send you a document, it will appear here.',
  },
  'profile.receivedOn': { ro: 'Primit', en: 'Received' },
  'profile.signedOn': { ro: 'semnat', en: 'signed' },
  'profile.docStatusSigned': { ro: 'Semnat', en: 'Signed' },
  'profile.docStatusCancelled': { ro: 'Anulat', en: 'Cancelled' },
  'profile.viewAndSign': { ro: 'Vezi și semnează', en: 'View and sign' },
  'profile.view': { ro: 'Vezi', en: 'View' },

  'profile.revokePasskeyTitle': { ro: 'Revocă passkey-ul?', en: 'Revoke this passkey?' },
  'profile.revokePasskeyMessage': {
    ro: 'Nu vei mai putea folosi acest passkey pentru autentificare sau confirmări biometrice.',
    en: 'You will no longer be able to use this passkey to sign in or confirm actions.',
  },
  'profile.revoke': { ro: 'Revocă', en: 'Revoke' },

  'profile.confirmIdentityToSign': { ro: 'Confirmă identitatea ca să semnezi acest document.', en: 'Confirm your identity to sign this document.' },
  'profile.signWithPasskey': { ro: 'Semnează cu passkey', en: 'Sign with passkey' },
  'profile.orEnterPassword': { ro: 'sau introdu parola', en: 'or enter your password' },
  'profile.accountPassword': { ro: 'Parola contului', en: 'Account password' },
  'profile.signWithPassword': { ro: 'Semnează cu parola', en: 'Sign with password' },
  'profile.alreadySigned': { ro: 'Ai semnat deja acest document.', en: 'You have already signed this document.' },
  'profile.cancelledByStaff': { ro: 'Acest document a fost anulat de personal.', en: 'This document was cancelled by staff.' },

  'profile.chooseImageFile': { ro: 'Alege un fișier imagine (JPEG, PNG etc.).', en: 'Choose an image file (JPEG, PNG, etc.).' },
  'profile.pictureUpdatedToast': { ro: 'Poza de profil a fost actualizată.', en: 'Profile picture updated.' },
  'profile.savePictureError': { ro: 'Nu am putut salva poza de profil.', en: 'We could not save the profile picture.' },
  'profile.processImageErrorFile': {
    ro: 'Nu am putut procesa imaginea — încearcă alt fișier.',
    en: 'We could not process the image — try a different file.',
  },
  'profile.processImageErrorRetry': {
    ro: 'Nu am putut procesa imaginea — încearcă din nou.',
    en: 'We could not process the image — try again.',
  },
  'profile.cameraAccessError': {
    ro: 'Nu am putut accesa camera. Verifică permisiunile browserului.',
    en: 'We could not access the camera. Check your browser permissions.',
  },
  'profile.removePictureError': { ro: 'Nu am putut șterge poza de profil.', en: 'We could not remove the profile picture.' },
  'profile.pictureRemovedToast': { ro: 'Poza de profil a fost ștearsă.', en: 'Profile picture removed.' },
  'profile.passkeyAddedToast': { ro: 'Passkey adăugat.', en: 'Passkey added.' },
  'profile.addPasskeyError': { ro: 'Nu am putut adăuga passkey-ul.', en: 'We could not add the passkey.' },
  'profile.passkeyRevokedToast': { ro: 'Passkey revocat.', en: 'Passkey revoked.' },
  'profile.revokePasskeyError': { ro: 'Nu am putut revoca passkey-ul.', en: 'We could not revoke the passkey.' },
  'profile.openDocumentError': { ro: 'Nu am putut deschide documentul.', en: 'We could not open the document.' },
  'profile.documentSignedToast': { ro: 'Documentul a fost semnat.', en: 'The document has been signed.' },
  'profile.enterAccountPassword': { ro: 'Introdu parola contului.', en: 'Enter your account password.' },
  'profile.incorrectPassword': { ro: 'Parolă incorectă.', en: 'Incorrect password.' },
  'profile.biometricSignFailed': {
    ro: 'Confirmarea biometrică a eșuat — poți folosi parola.',
    en: 'Biometric confirmation failed — you can use your password.',
  },
  'profile.biometricNotWorking': {
    ro: 'Confirmarea biometrică nu a funcționat — poți folosi parola.',
    en: 'Biometric confirmation did not work — you can use your password.',
  },
};
