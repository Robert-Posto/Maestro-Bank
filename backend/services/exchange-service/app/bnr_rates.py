"""Client pentru feed-ul OFICIAL, public, gratuit al Băncii Naționale a
României cu cursurile de referință zilnice.

    https://curs.bnr.ro/nbrfxrates.xml

Actualizat de BNR o dată pe zi lucrătoare (~13:00). NU necesită API key,
NU are rate-limit documentat, e exact sursa folosită și de bănci/fintech-uri
reale din România pentru cursul de referință — de-aia am ales asta în loc
de scraping (fragil, adesea interzis prin ToS) sau un API plătit.

Exemplu structură XML (simplificat, verificat live la implementare):

    <DataSet xmlns="https://www.bnr.ro/xsd">
      <Body>
        <Cube date="2026-08-19">
          <Rate currency="EUR">5.2442</Rate>
          <Rate currency="USD">4.5298</Rate>
          <Rate currency="HUF" multiplier="100">1.4388</Rate>
          ...
        </Cube>
      </Body>
    </DataSet>

`multiplier` (implicit 1) apare la valute unde BNR publică rata per N
unități (ex. HUF/JPY per 100) — o gestionăm defensiv, deși EUR/USD/GBP
(singurele din dataset-ul MaestroBank) au mereu multiplier 1.

NOTĂ: namespace-ul XML e "https://www.bnr.ro/xsd" (cu https) — BNR l-a
schimbat de la http:// la un moment dat; dacă parsarea începe brusc să nu
mai găsească <Cube>, primul loc de verificat e namespace-ul de mai jos.
"""

import xml.etree.ElementTree as ET

import httpx

from app.config import BNR_RATES_URL, SUPPORTED_FOREIGN_CURRENCIES

_NAMESPACE = {"bnr": "https://www.bnr.ro/xsd"}


async def fetch_bnr_rates() -> tuple[dict[str, float], str]:
    """Întoarce ({monedă: curs RON per 1 unitate}, data publicării "YYYY-MM-DD").

    Aruncă orice excepție httpx/ElementTree către apelant — decizia despre
    ce se întâmplă dacă eșuează (fallback etc.) NU se ia aici.
    """
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        response = await client.get(BNR_RATES_URL)
        response.raise_for_status()

    root = ET.fromstring(response.text)
    cube = root.find(".//bnr:Cube", _NAMESPACE)
    if cube is None:
        raise ValueError("Format BNR neașteptat: elementul <Cube> lipsește din XML.")

    rate_date = cube.get("date", "")
    rates: dict[str, float] = {}
    for rate_element in cube.findall("bnr:Rate", _NAMESPACE):
        currency = rate_element.get("currency")
        if currency not in SUPPORTED_FOREIGN_CURRENCIES or rate_element.text is None:
            continue
        multiplier = int(rate_element.get("multiplier", "1"))
        rates[currency] = float(rate_element.text) / multiplier

    missing = set(SUPPORTED_FOREIGN_CURRENCIES) - rates.keys()
    if missing:
        raise ValueError(f"Feed-ul BNR nu conținea cursuri pentru: {', '.join(sorted(missing))}.")

    return rates, rate_date
