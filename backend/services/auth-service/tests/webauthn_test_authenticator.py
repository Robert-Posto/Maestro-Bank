"""Authenticator WebAuthn minimal, DOAR pentru teste.

NU folosim pachetul `soft-webauthn` — verificat direct (pip install în
container): `soft-webauthn==0.1.4` cere `fido2>=1.0,<2.0`, iar `fido2==1.2.0`
cere `cryptography<45`, dar `webauthn==3.0.0` (pachetul real, din
requirements.txt) cere `cryptography>=49.0.0`. Cele două nu pot coexista în
același container — nu e o presupunere, e un conflict de dependințe
confirmat la instalare.

În loc, construim manual structurile WebAuthn (authenticatorData,
attestationObject CBOR, COSE_Key), semnate cu o cheie EC P-256 reală prin
`cryptography` (deja dependință a lui `webauthn`) + `cbor2` (idem) — fără
NICIO dependință nouă. NU mock-uim funcția de verificare din `webauthn`;
doar generăm intrări valide (sau, pentru testele negative, deliberat
invalide) pentru ea.
"""

import base64
import hashlib
import json
import os
import struct

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

_FLAG_USER_PRESENT = 0x01
_FLAG_USER_VERIFIED = 0x04
_FLAG_ATTESTED_CREDENTIAL_DATA = 0x40


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class SoftwareAuthenticator:
    """Un authenticator software cu o SINGURĂ credențială — suficient pentru
    testele din test_auth.py (nu simulează mai multe chei per RP)."""

    def __init__(self) -> None:
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(32)
        self.sign_count = 0

    def _public_key_cose(self) -> bytes:
        numbers = self.private_key.public_key().public_numbers()
        cose_key = {
            1: 2,  # kty: EC2
            3: -7,  # alg: ES256
            -1: 1,  # crv: P-256
            -2: numbers.x.to_bytes(32, "big"),
            -3: numbers.y.to_bytes(32, "big"),
        }
        return cbor2.dumps(cose_key)

    @staticmethod
    def _client_data_json(*, ceremony_type: str, challenge: bytes, origin: str) -> bytes:
        client_data = {
            "type": ceremony_type,
            "challenge": b64url(challenge),
            "origin": origin,
            "crossOrigin": False,
        }
        return json.dumps(client_data).encode("utf-8")

    def create(self, *, challenge: bytes, rp_id: str, origin: str, user_verified: bool = True) -> dict:
        """Simulează navigator.credentials.create() — răspuns de înregistrare."""
        client_data_json = self._client_data_json(ceremony_type="webauthn.create", challenge=challenge, origin=origin)

        flags = _FLAG_USER_PRESENT | _FLAG_ATTESTED_CREDENTIAL_DATA
        if user_verified:
            flags |= _FLAG_USER_VERIFIED

        rp_id_hash = hashlib.sha256(rp_id.encode("utf-8")).digest()
        aaguid = b"\x00" * 16
        attested_credential_data = (
            aaguid + struct.pack(">H", len(self.credential_id)) + self.credential_id + self._public_key_cose()
        )
        auth_data = rp_id_hash + bytes([flags]) + struct.pack(">I", self.sign_count) + attested_credential_data

        attestation_object = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})

        return {
            "id": b64url(self.credential_id),
            "rawId": b64url(self.credential_id),
            "type": "public-key",
            "clientExtensionResults": {},
            "response": {
                "clientDataJSON": b64url(client_data_json),
                "attestationObject": b64url(attestation_object),
            },
        }

    def get(
        self,
        *,
        challenge: bytes,
        rp_id: str,
        origin: str,
        user_verified: bool = True,
        user_handle: bytes | None = None,
    ) -> dict:
        """Simulează navigator.credentials.get() — răspuns de autentificare.

        Crește contorul de semnătură la FIECARE apel, ca un authenticator
        fizic real — esențial pentru testul de regresie a contorului
        (capturăm un răspuns, NU îl trimitem imediat, avansăm contorul
        printr-un alt apel, apoi retrimitem răspunsul vechi -> trebuie
        respins).
        """
        self.sign_count += 1

        client_data_json = self._client_data_json(ceremony_type="webauthn.get", challenge=challenge, origin=origin)

        flags = _FLAG_USER_PRESENT
        if user_verified:
            flags |= _FLAG_USER_VERIFIED

        rp_id_hash = hashlib.sha256(rp_id.encode("utf-8")).digest()
        auth_data = rp_id_hash + bytes([flags]) + struct.pack(">I", self.sign_count)

        client_data_hash = hashlib.sha256(client_data_json).digest()
        signature = self.private_key.sign(auth_data + client_data_hash, ec.ECDSA(hashes.SHA256()))

        response: dict = {
            "clientDataJSON": b64url(client_data_json),
            "authenticatorData": b64url(auth_data),
            "signature": b64url(signature),
        }
        if user_handle is not None:
            response["userHandle"] = b64url(user_handle)

        return {
            "id": b64url(self.credential_id),
            "rawId": b64url(self.credential_id),
            "type": "public-key",
            "clientExtensionResults": {},
            "response": response,
        }
