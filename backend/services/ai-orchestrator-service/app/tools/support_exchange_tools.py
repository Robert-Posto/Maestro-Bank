"""Tool-uri de schimb valutar pentru Support Agent — apelează EXCLUSIV
/api/exchange/* prin Gateway (vezi app/tools/_gateway_client.py).

`get_exchange_quote` cheamă EXACT același endpoint (`GET /exchange/quote`)
folosit de pagina Schimb valutar (vezi frontend/src/app/features/exchange) —
cursul REAL al zilei (BNR) + comisionul MaestroBank, calculate o singură
dată, în exchange-service, NU reinventate/aproximate de model. Înainte de
acest tool, o întrebare de tip "cât ar fi 100 RON în EUR?" nu avea nicio
sursă de adevăr — modelul fie refuza să răspundă, fie (mai rău) ghicea un
curs, ambele greșite pentru o bancă.
"""

from typing import Any

from app.tools._gateway_client import GatewayError, gateway_request


async def get_exchange_rates(authorization: str) -> Any:
    """Cursurile curente (mid_rate BNR + spread_percent + commission_minor)
    pentru toate valutele suportate — pentru o întrebare generală ("cât e
    cursul la euro azi?"), fără o sumă anume de convertit."""
    try:
        return await gateway_request("GET", "/api/exchange/rates", authorization)
    except GatewayError as exc:
        return {"error": exc.detail, "status_code": exc.status_code}


async def get_exchange_quote(authorization: str, from_currency: str, to_currency: str, amount: float) -> Any:
    """Cotație REALĂ (nu estimare) pentru schimbul unei sume dintr-o valută
    în alta — `amount` e în UNITĂȚI ÎNTREGI ale valutei sursă (ex. 100
    pentru "100 RON" sau "100 EUR"), NU în bani/cenți; conversia în minor
    units se face aici, determinist, ca modelul să nu greșească ordinul de
    mărime. `from_currency`/`to_currency` sunt coduri ISO de 3 litere
    (RON, EUR, USD, GBP). Întoarce inclusiv `received_minor` (suma primită,
    după comision) și `applied_rate` — folosește-le direct în răspuns, NU
    recalcula tu cursul."""
    amount_minor = round(amount * 100)
    if amount_minor <= 0:
        return {"error": "Suma trebuie să fie pozitivă."}
    try:
        return await gateway_request(
            "GET",
            "/api/exchange/quote",
            authorization,
            params={
                "from_currency": from_currency.upper(),
                "to_currency": to_currency.upper(),
                "amount_minor": amount_minor,
            },
        )
    except GatewayError as exc:
        return {"error": exc.detail, "status_code": exc.status_code}
