"""Execuția REALĂ a acțiunilor de scriere ale Support Agent asupra propriului
cont/carduri ale userului — apelată STRICT din
app/services/support_service.py::_execute_confirmed_action, DUPĂ ce userul a
confirmat explicit (niciodată din interiorul buclei GPT — vezi
app/agents/support.py::WRITE_TOOLS).

Graniță de securitate STRUCTURALĂ, nu doar convenție de prompt: fiecare
funcție de-aici rezolvă orice cont/card ȚINTĂ EXCLUSIV din datele proprii ale
userului autentificat (`get_my_accounts`/`get_my_cards`, ambele scopate prin
JWT-ul propagat, la fel ca orice tool de citire) — NICIUN parametru de-aici nu
acceptă un IBAN, un account_id sau un card_id brut. Modelul poate cel mult
alege UN TIP de cont (`account_type`, un enum fix) sau ultimele 4 cifre ale
UNUIA dintre cardurile proprii — e structural imposibil să trimită bani către
altcineva sau să atingă contul/cardul altui user, indiferent ce ar "convinge"
cineva modelul să ceară.
"""

from typing import Any

from app.tools._gateway_client import GatewayError, gateway_request
from app.tools.support_accounts_tools import get_my_accounts
from app.tools.support_cards_tools import get_my_cards

# Nu "current" — un transfer către propriul cont curent n-are sens (ar fi
# sursa și destinația același cont); vezi execute_internal_transfer.
_TRANSFERABLE_ACCOUNT_TYPES = {"savings", "deposit", "student", "eur", "usd", "gbp"}

# "student" exclus deliberat — accounts-service cere un document justificativ
# (AccountCreateRequest.document_filename), pe care un agent conversațional
# nu poate atașa real; "current"/"deposit" nu sunt deschidibile prin
# POST /accounts/new (vezi CreatableAccountType din accounts-service).
_OPENABLE_ACCOUNT_TYPES = {"savings", "eur", "usd", "gbp"}

_EXCHANGE_CURRENCIES = {"RON", "EUR", "USD", "GBP"}


async def execute_internal_transfer(authorization: str, to_account_type: str, amount: float) -> dict[str, Any]:
    """Transfer STRICT între conturile proprii ale userului — din contul
    curent (mereu sursa, la fel ca la un transfer normal — vezi
    transactions-service::TransferRequest, sursa vine din JWT, niciodată din
    input) către un alt cont propriu, ales după TIP, nu după IBAN."""
    normalized_type = to_account_type.strip().lower()
    if normalized_type not in _TRANSFERABLE_ACCOUNT_TYPES:
        return {
            "error": f"Tip de cont invalid pentru transfer intern: „{to_account_type}”.",
            "status_code": 422,
        }
    if amount <= 0:
        return {"error": "Suma trebuie să fie un număr pozitiv.", "status_code": 422}

    accounts = await get_my_accounts(authorization)
    if isinstance(accounts, dict) and "error" in accounts:
        return accounts
    target = next((a for a in accounts if a.get("account_type") == normalized_type), None)
    if target is None:
        return {
            "error": f"Nu ai încă un cont de tip „{normalized_type}” — deschide-l mai întâi din pagina Conturi.",
            "status_code": 404,
        }

    try:
        transfer = await gateway_request(
            "POST",
            "/api/transactions/transfers",
            authorization,
            json={
                "to_iban": target["iban"],
                "amount_minor": round(amount * 100),
                "description": f"Transfer intern către contul propriu ({normalized_type})",
                "category": "other",
            },
        )
    except GatewayError as exc:
        return {"error": exc.detail, "status_code": exc.status_code}
    return {"transfer": transfer, "to_account_type": normalized_type}


async def _resolve_card_id(authorization: str, last_four: str | None) -> str | dict[str, Any]:
    """Rezolvă id-ul REAL al unui card propriu — după `last_four`, sau
    primul card al userului dacă nu e specificat (la fel ca
    support_cards_tools.get_card_status). Întoarce un dict cu `error` dacă
    nu găsește nimic — apelantul îl propagă direct ca rezultat."""
    cards = await get_my_cards(authorization)
    if isinstance(cards, dict) and "error" in cards:
        return cards
    if not cards:
        return {"error": "Nu ai niciun card.", "status_code": 404}
    if last_four:
        match = next((c for c in cards if c.get("last_four") == last_four), None)
        if match is None:
            return {"error": f"Nu există niciun card cu ultimele 4 cifre {last_four}.", "status_code": 404}
        return match["id"]
    return cards[0]["id"]


async def execute_update_card_settings(
    authorization: str,
    last_four: str | None = None,
    freeze: bool | None = None,
    online_payments_enabled: bool | None = None,
    contactless_enabled: bool | None = None,
    atm_withdrawals_enabled: bool | None = None,
    international_payments_enabled: bool | None = None,
    daily_limit: float | None = None,
) -> dict[str, Any]:
    """Aplică una sau mai multe schimbări asupra UNUI card propriu, rezolvat
    STRICT din cardurile userului (vezi _resolve_card_id) — niciodată dintr-un
    card_id primit direct. Fiecare câmp e opțional; doar cele trimise (Not
    None) sunt aplicate, exact ca la CardSettingsUpdate din accounts-service."""
    card_id = await _resolve_card_id(authorization, last_four)
    if isinstance(card_id, dict):
        return card_id

    card: dict[str, Any] | None = None
    try:
        if freeze is not None:
            path = f"/api/accounts/cards/{card_id}/freeze" if freeze else f"/api/accounts/cards/{card_id}/unfreeze"
            card = await gateway_request("PATCH", path, authorization)

        settings_fields = {
            "online_payments_enabled": online_payments_enabled,
            "contactless_enabled": contactless_enabled,
            "atm_withdrawals_enabled": atm_withdrawals_enabled,
            "international_payments_enabled": international_payments_enabled,
        }
        settings_fields = {k: v for k, v in settings_fields.items() if v is not None}
        if settings_fields:
            card = await gateway_request(
                "PATCH", f"/api/accounts/cards/{card_id}/settings", authorization, json=settings_fields
            )

        if daily_limit is not None:
            if daily_limit <= 0:
                return {"error": "Limita zilnică trebuie să fie un număr pozitiv.", "status_code": 422}
            card = await gateway_request(
                "PATCH",
                f"/api/accounts/cards/{card_id}/limits",
                authorization,
                json={"daily_limit_minor": round(daily_limit * 100)},
            )
    except GatewayError as exc:
        return {"error": exc.detail, "status_code": exc.status_code}

    if card is None:
        return {"error": "Nu a fost specificată nicio schimbare de aplicat.", "status_code": 422}
    return {"card": card}


async def execute_open_account(authorization: str, account_type: str) -> dict[str, Any]:
    """Deschide un cont NOU al userului — DOAR tipuri fără document necesar
    (vezi _OPENABLE_ACCOUNT_TYPES). accounts-service validează el însuși
    limita de "un cont per tip" (409, mesaj deja clar) — nu duplicăm
    verificarea aici, doar propagăm eroarea reală."""
    normalized_type = account_type.strip().lower()
    if normalized_type not in _OPENABLE_ACCOUNT_TYPES:
        return {
            "error": f"Tip de cont invalid sau care nu poate fi deschis prin conversație: „{account_type}”.",
            "status_code": 422,
        }
    try:
        account = await gateway_request(
            "POST", "/api/accounts/new", authorization, json={"account_type": normalized_type}
        )
    except GatewayError as exc:
        return {"error": exc.detail, "status_code": exc.status_code}
    return {"account": account}


async def execute_currency_exchange(authorization: str, from_currency: str, to_currency: str, amount: float) -> dict[str, Any]:
    """Schimb valutar REAL — curs BNR + comision MaestroBank (vezi
    exchange-service), STRICT între conturile PROPRII ale userului pe cele
    două valute (nu există parametru de beneficiar — schimbul valutar e prin
    natura lui intern, contul sursă și cel destinație aparțin amândouă
    userului autentificat)."""
    from_normalized = from_currency.strip().upper()
    to_normalized = to_currency.strip().upper()
    if from_normalized not in _EXCHANGE_CURRENCIES or to_normalized not in _EXCHANGE_CURRENCIES:
        return {"error": f"Valută invalidă: „{from_currency}” sau „{to_currency}”.", "status_code": 422}
    if from_normalized == to_normalized:
        return {"error": "Valuta sursă și cea destinație trebuie să fie diferite.", "status_code": 422}
    if amount <= 0:
        return {"error": "Suma trebuie să fie un număr pozitiv.", "status_code": 422}

    try:
        exchange = await gateway_request(
            "POST",
            "/api/exchange/execute",
            authorization,
            json={"from_currency": from_normalized, "to_currency": to_normalized, "amount_minor": round(amount * 100)},
        )
    except GatewayError as exc:
        return {"error": exc.detail, "status_code": exc.status_code}
    return {"exchange": exchange}
