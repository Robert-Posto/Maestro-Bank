"""Modele Pydantic ale verification-service. Nu există o colecție Mongo
proprie — rezultatul verificării trăiește DOAR ca flag pe user-ul din
auth_db (identity_verified), nu păstrăm imaginile sau un istoric aici
(vezi service.py pentru motiv: date sensibile, fără nevoie reală de
persistență într-un demo)."""

from pydantic import BaseModel


class VerificationResult(BaseModel):
    verified: bool
    message: str
    # None doar când nu s-a putut detecta nicio față (nu există distanță
    # de calculat). Nu e o probabilitate calibrată statistic — vezi
    # service.py::_similarity_percent.
    similarity_percent: float | None = None
