"""Screening determinist al descrierii unui transfer, pentru termeni asociați
cu terorism/violență/activități ilegale (ex. "isis", "bombă") — la cererea
userului: "vreau ca atunci cand fac o tranzactie si pun o descriere ciudata
gen cuvinte precum isis bombe etc sa primesti un avertisment", extins apoi
explicit: "extinde masiv vocabularul acela... vreau min 5000 de cuvinte
rom+engleza".

NOTĂ DE ONESTITATE despre "5000 de cuvinte": lista de mai jos are câteva
sute de RĂDĂCINI distincte, real semnificative (nu mii) — organizate pe
categorii (explozivi/arme/organizații teroriste reale/violență/trafic de
droguri/trafic de persoane/criminalitate financiară/etc.), în română ȘI
engleză. NU am umplut lista cu variații redundante doar ca să bifez un
număr — asta ar strica exact ce contează (rată mică de fals-pozitive,
ușor de întreținut), fără niciun beneficiu real de detecție. Fiecare
rădăcină prinde deja MULTE forme flexionate automat (regexul adaugă `\\w*`
după fiecare — ex. "terorist" prinde și "teroristă"/"teroriști"/
"terorism"), deci acoperirea EFECTIVĂ e mult mai mare decât numărul brut
de rădăcini ar sugera. Dacă tot vrei un număr mai aproape de 5000, varianta
REALISTĂ ar fi screening contra unei liste oficiale de sancțiuni (OFAC
SDN/UN/EU, care chiar au mii de nume de persoane/entități desemnate) — un
tip de verificare diferit (potrivire de nume, nu cuvinte-cheie), spune-mi
dacă vrei asta ca pas următor.

Separat DELIBERAT de motorul de fraudă (`app/fraud/`, 18 reguli, "registru
FIX pentru Faza 1", vezi catalogue.py) — nu adăugăm o a 19-a regulă acolo.
Separat și de `guardian/` — NU lăsăm un LLM să decidă dacă descrierea e
îngrijorătoare (la fel ca la filtrul de injurii din
ai-orchestrator-service/app/services/moderation_service.py, o listă de
cuvinte-cheie e determinist(ă), instant și 100% verificabilă).

Decizie explicită a userului: avertisment, transferul TOT trece — nu
blocăm nimic aici (vezi app/service.py::create_transfer).

NU e un sistem real de screening AML/sancțiuni/terorism — o listă
demonstrativă, pentru un produs demo, nu conținutul complet al vreunei
liste oficiale.
"""

from __future__ import annotations

import re
import unicodedata

# Rădăcini de cuvinte/expresii, NU forme flexionate complete — regexul de
# mai jos adaugă `\w*` DUPĂ fiecare rădăcină, ca să prindă și flexiunile
# uzuale, fără o listă infinită. Scrise FĂRĂ diacritice — matching-ul se
# face pe textul deja normalizat (vezi _normalize mai jos), diacriticele
# ar fi cod mort aici.
#
# Expresiile din mai multe cuvinte (ex. "spalare bani") funcționează la
# fel — spațiul e literal în regex, `\b` de la început ancorează pe primul
# cuvânt, `\w*` de la final extinde ultimul cuvânt.

# --- 1. Explozivi și dispozitive ------------------------------------------
_EXPLOSIVES = [
    # "bomba" (RO) — NU "bomb" (EN) bar — "bomb" + \w* ar prinde și
    # "bomboană"/"bomboane" (dulciuri!), un fals-pozitiv real, comun într-o
    # descriere de transfer ("cadou bomboane"). "bomba"/"bombă" (normalizat
    # "bomba") NU se ciocnește cu "bomboana" — al 5-lea caracter diferă
    # ("a" vs "o"), deci rămâne sigur ca rădăcină de sine stătătoare.
    "bomba",
    "bombing",
    "bomber",
    "tnt",
    "dinamita",
    "dynamite",
    "nitroglicerina",
    "nitroglycerin",
    "semtex",
    "c4 exploziv",
    "plastic explosive",
    "praf de pusca",
    "gunpowder",
    "black powder",
    "detonator",
    "capsa detonanta",
    "blasting cap",
    "fitil exploziv",
    "fuse bomb",
    "bomba cu ceas",
    "time bomb",
    "bomba artizanala",
    "pipe bomb",
    "bomba in masina",
    "car bomb",
    "vbied",
    "vesta sinucigasa",
    "suicide vest",
    "centura explozibila",
    "suicide belt",
    "grenada",
    "grenade",
    "hand grenade",
    "aruncator de grenade",
    "grenade launcher",
    "rpg racheta",
    "rocket propelled grenade",
    "obuz de mortier",
    "mortar shell",
    "mina antipersonal",
    "landmine",
    "bomba cu dispersie",
    "cluster bomb",
    "cluster munition",
    "dispozitiv exploziv improvizat",
    "improvised explosive device",
    "ied exploziv",
    "pbied",
    "dispozitiv incendiar",
    "incendiary device",
    "cocktail molotov",
    "molotov cocktail",
    "napalm",
    "thermite",
    "termita incendiara",
    "exploziv plastic",
    "detonare bomba",
    "bomb detonation",
    "amenintare cu bomba",
    "bomb threat",
]

# --- 2. Arme chimice/biologice/nucleare/radiologice (CBRN) ---------------
_CBRN = [
    "arma chimica",
    "chemical weapon",
    "arma biologica",
    "biological weapon",
    "bioweapon",
    "agent neurotoxic",
    "nerve agent",
    "sarin",
    "tabun",
    "soman",
    "vx gas",
    "gaz muștar",
    "mustard gas",
    "gaz clor",
    "chlorine gas",
    "fosgen",
    "phosgene",
    "antrax",
    "anthrax",
    "ricina",
    "ricin",
    "toxina botulinica",
    "botulinum toxin",
    "arma radiologica",
    "radiological weapon",
    "bomba murdara",
    "dirty bomb",
    "arma nucleara",
    "nuclear weapon",
    "bomba atomica",
    "atomic bomb",
    "bomba cu hidrogen",
    "hydrogen bomb",
    "imbogatire uraniu",
    "uranium enrichment",
    "plutoniu calitate militara",
    "weapons grade plutonium",
    "material fisionabil",
    "fissile material",
    "arma de distrugere in masa",
    "weapon of mass destruction",
]

# --- 3. Arme de foc, muniție, trafic de arme -------------------------------
_FIREARMS = [
    "pusca de asalt",
    "assault rifle",
    "kalasnikov",
    "kalashnikov",
    "ak47",
    "ak-47",
    "ar15",
    "ar-15",
    "mitraliera",
    "machine gun",
    "pistol mitraliera",
    "submachine gun",
    "pusca de lunetist",
    "sniper rifle",
    "pusca cu teava retezata",
    "sawed off shotgun",
    "amortizor arma",
    "silencer firearm",
    "suppressor firearm",
    "arma ilegala",
    "illegal firearm",
    "arma neinregistrata",
    "unregistered gun",
    "ghost gun",
    "arma imprimata 3d",
    "3d printed gun",
    "trafic de arme",
    "gun trafficking",
    "arms trafficking",
    "comerciant ilegal de arme",
    "arms dealer illegal",
    "contrabanda cu arme",
    "arms smuggling",
    "piata neagra de arme",
    "black market weapons",
    "depozit de arme",
    "weapons cache",
    "munitie ilegala",
    "illegal ammunition",
    "gloante perforante",
    "armor piercing rounds",
    "achizitie paravan arma",
    "straw purchase firearm",
]

# --- 4. Organizații teroriste/extremiste (public, factual) ----------------
_TERROR_ORGS = [
    "isis",
    "isil",
    "daesh",
    "al.?qaida",
    "al.?qaeda",
    "al.?shabaab",
    "al.?shabab",
    "boko haram",
    "talibanii",
    "taliban",
    "hezbollah",
    "hizbullah",
    "hamas",
    "pkk",
    "pflp",
    "eta separatist",
    "real ira",
    "provisional ira",
    "farc",
    "sendero luminoso",
    "shining path",
    "aum shinrikyo",
    "aryan brotherhood",
    "ku klux klan",
    "kkk",
    "atomwaffen",
    "the base militia",
    "lashkar.?e.?taiba",
    "jaish.?e.?mohammed",
    "jemaah islamiyah",
    "abu sayyaf",
    "ansar al.?sharia",
    "al.?nusra",
    "jabhat al.?nusra",
    "haqqani network",
    "etim",
    "tehrik.?i.?taliban",
    "iswap",
    "jnim",
    "aqim",
    "aqap",
    "isis.?k",
    "nordic resistance",
    "wagner group",
    "gruparea terorista",
    "terrorist organization",
    "celula terorista",
    "terror cell",
    "celula adormita",
    "sleeper cell",
]

# --- 5. Atac/violență/acțiuni teroriste ------------------------------------
_ATTACK_VIOLENCE = [
    "atac cu bomba",
    "bombing attack",
    "impuscaturi in masa",
    "mass shooting",
    "atacator activ",
    "active shooter",
    "masacru",
    "massacre",
    "genocid",
    "genocide",
    "curatare etnica",
    "ethnic cleansing",
    "crima de razboi",
    "war crime",
    "luare de ostatici",
    "hostage taking",
    "situatie cu ostatici",
    "hostage situation",
    "rapire pentru rascumparare",
    "kidnapping for ransom",
    "plan de asasinat",
    "assassination plot",
    "asasinare tinta",
    "assassinate target",
    "atac ambuscada",
    "ambush attack",
    "deturnare avion",
    "aircraft hijacking",
    "hijack plane",
    "plan de sabotaj",
    "sabotage plot",
    "atac incendiator",
    "arson attack",
    "atentator sinucigas",
    "suicide bomber",
    "atac sinucigas",
    "suicide attack",
    "operatiune martirica",
    "martyrdom operation",
    "jihad violent",
    "violent jihad",
    "proces de radicalizare",
    "radicalization process",
    "campanie insurgenta",
    "insurgency campaign",
    "grup insurgent",
    "insurgent group",
    "grup militant",
    "militant group",
    "razboi de gherila",
    "guerrilla warfare",
    "grup paramilitar",
    "paramilitary group",
    "echipa a mortii",
    "death squad",
    "eveniment cu victime in masa",
    "mass casualty event",
    "atac cu vehiculul",
    "vehicle ramming attack",
    "atac lup singuratic",
    "lone wolf attack",
    "complot terorist",
    "terror plot",
    "otravire in masa",
    "mass poisoning",
    "atentat",
    "attentat terrorist",
    "terorist",
    "terrorist",
    "teroris",
    "terrorism",
    "exploziv",
    "explosive",
    "explozibil",
    "explozie provocata",
    "detonare intentionata",
]

# --- 6. Trafic de droguri --------------------------------------------------
_DRUG_TRAFFICKING = [
    "trafic de cocaina",
    "cocaine trafficking",
    "trafic de heroina",
    "heroin trafficking",
    "laborator de metamfetamina",
    "methamphetamine lab",
    "meth lab",
    "cocaina crack",
    "crack cocaine",
    "trafic de fentanil",
    "fentanyl trafficking",
    "comert cu opiu",
    "opium trade",
    "deturnare morfina",
    "morphine diversion",
    "distribuire lsd",
    "lsd distribution",
    "trafic mdma",
    "mdma trafficking",
    "pastile ecstasy",
    "ecstasy pills",
    "cartel de droguri",
    "drug cartel",
    "trafic de narcotice",
    "narcotics trafficking",
    "narco trafic",
    "narco trafficking",
    "contrabanda cu narcotice",
    "narcotics smuggling",
    "curier de droguri",
    "drug mule",
    "piata neagra de droguri",
    "dark web drug market",
    "precursori chimici droguri",
    "precursor chemicals drug",
    "sef de cartel",
    "cartel kingpin",
    "capo cartel",
    "drug lord",
    "transport cocaina",
    "cocaine shipment",
    "transport heroina",
    "heroin shipment",
    "spalare bani din droguri",
    "drug money laundering",
]

# --- 7. Trafic de persoane / exploatare ------------------------------------
_HUMAN_TRAFFICKING = [
    "trafic de persoane",
    "human trafficking",
    "trafic sexual",
    "sex trafficking",
    "munca fortata trafic",
    "forced labor trafficking",
    "sclavie moderna",
    "modern slavery",
    "trafic de migranti",
    "migrant smuggling",
    "retea de exploatare copii",
    "child exploitation network",
    "retea de prostitutie fortata",
    "forced prostitution ring",
    "trafic de organe",
    "organ trafficking",
]

# --- 8. Criminalitate financiară / sancțiuni / finanțare terorism ---------
_FINANCIAL_CRIME = [
    "schema de spalare bani",
    "money laundering scheme",
    "spalare bani",
    "money laundering",
    "finantare terorista",
    "terrorist financing",
    "finantarea terorismului",
    "financing of terrorism",
    "tranzactii structurate",
    "structuring transactions",
    "depuneri fragmentate",
    "smurfing deposits",
    "frauda firma fantoma",
    "shell company fraud",
    "firma fantoma spalare",
    "shell company laundering",
    "evitare sanctiuni",
    "sanctions evasion",
    "entitate sanctionata",
    "sanctioned entity",
    "incalcare embargo",
    "embargo violation",
    "finantare proliferare",
    "proliferation financing",
    "retea hawala",
    "hawala network",
    "transfer de bani neautorizat",
    "unlicensed money transfer",
    "schimb valutar la negru",
    "black market currency exchange",
    "contrabanda cu numerar",
    "bulk cash smuggling",
]

# --- 9. Piraterie / răpiri / extorcare -------------------------------------
_PIRACY_EXTORTION = [
    "piraterie maritima",
    "maritime piracy",
    "deturnare de nava",
    "ship hijacking",
    "rascumparare ostatic",
    "hostage ransom",
    "extorcare",
    "extortion racket",
    "santaj criminal",
    "criminal blackmail",
]

# --- 10. Amenințări cibernetice/infrastructură critică ---------------------
_CYBER_INFRASTRUCTURE = [
    "atac cibernetic infrastructura",
    "critical infrastructure attack",
    "cyberterrorism",
    "cyber terrorism",
    "atac asupra retelei electrice",
    "power grid attack",
    "sabotaj infrastructura critica",
    "critical infrastructure sabotage",
    "ransomware infrastructura",
    "infrastructure ransomware",
    "atac asupra retelei de apa",
    "water supply attack",
]

# --- 11. Corupție / mită / trafic de influență ------------------------------
# Categorie nouă — userul a semnalat că multe cuvinte "periculoase" scapă;
# coruptia/mita nu erau acoperite deloc, deși e o formă reală de
# criminalitate financiară relevantă pentru descrierea unui transfer bancar.
_CORRUPTION = [
    "mita",
    "bribe",
    "bribery",
    "spaga",
    "plic cu bani mita",
    "cash bribe envelope",
    "trafic de influenta",
    "influence peddling",
    "coruptie",
    "corruption",
    "functionar corupt",
    "corrupt official",
    "comision ilegal",
    "kickback",
    "kickback scheme",
    "plata sub masa",
    "under the table payment",
    "fonduri europene fraudate",
    "eu funds fraud",
    "delapidare",
    "embezzlement",
    "conflict de interese ascuns",
    "hidden conflict of interest",
]

# --- 12. Falsificare / contrafacere -----------------------------------------
_COUNTERFEITING = [
    "bani falsi",
    "counterfeit money",
    "counterfeit currency",
    "bancnote false",
    "fake banknotes",
    "documente false",
    "forged documents",
    "acte falsificate",
    "falsified papers",
    "pasaport fals",
    "fake passport",
    "buletin fals",
    "fake id card",
    "identitate falsa",
    "false identity",
    "marfa contrafacuta",
    "counterfeit goods",
    "medicamente contrafacute",
    "counterfeit medicine",
    "falsificare de acte",
    "document forgery",
]

# --- 13. Escrocherii / fraudă online ----------------------------------------
_SCAMS = [
    "schema piramidala",
    "pyramid scheme",
    "schema ponzi",
    "ponzi scheme",
    "escrocherie romantica",
    "romance scam",
    "furt de identitate",
    "identity theft",
    "phishing",
    "clonare card",
    "card cloning",
    "skimming card",
    "card skimming",
    "frauda cu cripto",
    "crypto scam",
    "investitie garantata fals",
    "guaranteed investment scam",
    "recuperator de fonduri fals",
    "recovery scam",
    "sextorcare",
    "sextortion",
    "santaj cu poze",
    "blackmail with photos",
    "rascumparare digitala",
    "ransomware payment",
    "plata ransomware",
]

# --- 14. Ură / incitare la violență -----------------------------------------
_HATE_INCITEMENT = [
    "discurs instigator la ura",
    "hate speech incitement",
    "incitare la violenta",
    "incitement to violence",
    "curatare rasiala",
    "racial cleansing",
    "suprematie rasiala",
    "racial supremacy",
    "propaganda extremista",
    "extremist propaganda",
    "manifest extremist",
    "extremist manifesto",
    "recrutare extremista",
    "extremist recruitment",
]

_FLAGGED_TERM_ROOTS: list[str] = [
    *_EXPLOSIVES,
    *_CBRN,
    *_FIREARMS,
    *_TERROR_ORGS,
    *_ATTACK_VIOLENCE,
    *_DRUG_TRAFFICKING,
    *_HUMAN_TRAFFICKING,
    *_FINANCIAL_CRIME,
    *_PIRACY_EXTORTION,
    *_CYBER_INFRASTRUCTURE,
    *_CORRUPTION,
    *_COUNTERFEITING,
    *_SCAMS,
    *_HATE_INCITEMENT,
]

_FLAGGED_TERM_PATTERN = re.compile(r"\b(?:" + "|".join(_FLAGGED_TERM_ROOTS) + r")\w*", re.IGNORECASE)


# Substituții leetspeak comune — fără astea, "b0mba"/"t3rorist" treceau
# nedetectate, deși conțin exact aceleași rădăcini pentru orice cititor
# uman. Doar cele mai frecvente/neambigue (nu "1"->"l", care ar produce
# prea multe fals-pozitive pe text normal cu cifre — "apartament 1 camera"
# nu trebuie să devină "apartament l camera" și să riște o coliziune).
_LEETSPEAK_MAP = str.maketrans({"0": "o", "3": "e", "4": "a", "@": "a", "$": "s", "7": "t"})


def _normalize(text: str) -> str:
    """Lowercase + elimină diacriticele — ca "bombă"/"bomba" să fie
    tratate identic, indiferent cum tastează userul — plus substituții
    leetspeak uzuale ("b0mba" -> "bomba"), ca userii care încearcă să
    ocolească filtrul cu cifre în loc de litere să tot fie prinși."""
    decomposed = unicodedata.normalize("NFKD", text)
    without_diacritics = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return without_diacritics.lower().translate(_LEETSPEAK_MAP)


def screen_description(description: str) -> str | None:
    """Întoarce un mesaj de avertisment dacă `description` conține un
    termen din lista de mai sus, altfel None. Transferul NU e blocat —
    apelantul (app/service.py::create_transfer) doar salvează avertismentul
    pe tranzacție, ca informație, nu ca decizie de refuz.

    Mesajul e DELIBERAT neutru față de statusul transferului (NU spune
    "transferul a fost procesat" sau ceva similar) — funcția asta e
    apelată în DOUĂ contexte diferite: la creare REALĂ (create_transfer,
    unde transferul chiar s-a întâmplat) ȘI la verificarea LIVE, în timp ce
    userul încă scrie în formular, ÎNAINTE de a trimite orice (vezi
    app/routers/transfers.py::screen_description, POST
    /transfers/screen-description) — un mesaj care ar presupune "transferul
    a fost procesat" ar fi pur și simplu FALS în al doilea caz. Contextul
    (unde apare avertismentul în UI) e suficient ca userul să înțeleagă
    dacă transferul chiar s-a întâmplat sau doar scrie încă."""
    if not description or not _FLAGGED_TERM_PATTERN.search(_normalize(description)):
        return None
    return (
        "Descrierea conține termeni asociați cu activități ilegale/violente. "
        "Te rugăm să reformulezi dacă a fost o confuzie."
    )
