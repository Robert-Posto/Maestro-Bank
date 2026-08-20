"""Eroare comună pentru toate tool-urile — vezi task-ul, secțiunea 21:
"Nu returna stack trace userului." Fiecare tool prinde erorile httpx și le
traduce într-un mesaj clar, în română, fără detalii interne.
"""


class ToolError(RuntimeError):
    """Un tool nu a putut obține datele cerute (microserviciu indisponibil,
    timeout, sau răspuns neașteptat). Mesajul e sigur de arătat userului.
    """
