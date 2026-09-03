# MaestroBank — Brief pentru Claude Design

*Document de context complet: ce e aplicația, identitatea ei vizuală reală, și conținutul integral al prezentării de demo day. Scopul: Claude Design poate lucra direct din acest document, fără context suplimentar.*

---

## 1. Despre aplicație

**MaestroBank** — o bancă digitală demo, construită de o echipă de 4 la AI Academy. Nu e o instituție financiară reală (fără Visa/Mastercard, SEPA, PSD2 sau integrare FX reale) — dar arhitectura, logica de fraudă, autentificarea și agenții AI sunt reale, nu simulate.

**Stack tehnic:**
- Frontend: Angular 22, componente standalone + signals (fără NgModules, fără store RxJS)
- Backend: 12 microservicii FastAPI, fiecare cu propria bază MongoDB
- Nginx (reverse proxy) → API Gateway (JWT, rutare, rate limiting) → microservicii
- Docker Compose pentru orchestrare

**Ce face aplicația (funcționalități reale):**
- Cont curent + carduri virtuale demo, transferuri IBAN-la-IBAN
- Motor de fraudă determinist (18+ reguli fixe) + **Financial Guardian** — un LLM separat, asincron, care doar EXPLICĂ o decizie deja luată (staff + client), niciodată nu decide
- Doi agenți AI peste GPT-5-mini, cu tool-calling real pe datele contului: MaestroAgent (buget/forecast, propune-nu-execută) și Support Agent (întrebări cont/card/tranzacții, propune tichete) — unificați recent într-un singur punct de intrare în sidebar
- Autentificare fără parolă (WebAuthn/passkeys) + step-up pentru acțiuni sensibile
- Verificare de identitate biometrică (DeepFace — comparație ID + selfie)
- Schimb valutar cu curs oficial BNR, live (nu simulat)
- Depozite la termen, investiții (catalog demo), credite personale (eligibilitate + rată automată), puncte de loialitate
- Interfață completă RO/EN (i18n)
- Consolă separată de staff (`/admin`) pentru revizuirea rețineerilor de fraudă

**Poziționare:** nu doar o aplicație de consumator — un **core bancar modular**. Fiecare capabilitate (fraudă, agenți AI, autentificare, conturi) e un serviciu independent, cu API propriu — o arhitectură care s-ar preta la banking-as-a-service (infrastructură licențiabilă altor fintech-uri), nu doar la un produs unic.

**Echipa:**
| Nume | Rol |
|---|---|
| Robert | Arhitectură & orchestrare (Gateway) + verificare de identitate (DeepFace) |
| Octavia | Agenți AI (MaestroAgent + Support, unificați) + Investiții + Credite + Puncte |
| Calin | Nucleu bancar + securitate/fraudă + Financial Guardian + passkey + eSign + i18n |
| Alex | Testare + remediere bug-uri + polish frontend |

---

## 2. Identitate vizuală (din design tokens-urile reale ale aplicației)

**Paletă (navy + accent albastru):**
- `#0a1226` — navy cel mai închis (fundal principal)
- `#142248` — navy ridicat (carduri/suprafețe)
- `#1c2f5e` — navy mediu
- `#2f6fed` — albastru accent (primar)
- `#2557d6` — albastru accent, mai închis (hover/active)
- `#eef4ff` — albastru foarte deschis (fundaluri tinte, pe temă luminoasă)
- Alb (`#ffffff`) — suprafețe pe temă luminoasă
- Verde `#16a34a` / roșu `#dc2626` — semantic (pozitiv/negativ), folosit rar, nu ca accent principal

Aplicația reală are și o temă luminoasă (alb/navy pe text) — dar pentru prezentare am ales varianta **navy închis, single-theme**, mai potrivită pentru proiecție pe scenă.

**Tipografie:**
- Aplicația reală: Inter (întreg, corp text + titluri)
- Prezentarea: Inter (corp text, consistent cu aplicația) + **Bricolage Grotesque** (titluri/cifre mari — o alegere distinctă, nu Inter/Space Grotesk peste tot, ca titlurile să aibă personalitate proprie)

**Ton:** modern, fintech, minimalist, încrezător — fără gradient-uri corporate clasice, fără emoji ca marcatori de secțiune, fără clișee de "AI design" (crem+serif, gradient mov-albastru).

---

## 3. Prezentarea — conținut complet, slide cu slide

**Context:** 20-30 minute (demo inclus), demo day AI Academy, public = mentori + manageri. Prezentator unic (Robert). Demo LA FINAL. Structură aprobată, 9 slide-uri.

**Regulă de titlu:** un singur titlu mare pe slide (nu o etichetă mică + titlu separat). Dacă un slide are puțin conținut, se centrează vertical pe slide, nu rămâne lipit sus cu spațiu gol dedesubt.

### Slide 1 — Deschidere
**Conținut:** doar "MaestroBank", mare, centrat. Nimic altceva.

### Slide 2 — Problema
**Titlu:** Problema
**4 carduri:**
- Fraudă explicată, nu doar blocată
- Asistență care acționează, nu doar răspunde la FAQ
- Autentificare fără fricțiune (fără parole)
- Date reale, nu simulate

### Slide 3 — Poziționare
**Titlu:** Poziționare
**Statement mare:** "Nu doar o aplicație. Un core bancar modular."
**Vizual:** 12 blocuri mici → săgeată → eticheta "banking-as-a-service"

### Slide 4 — Echipa
**Titlu:** Echipa
**4 carduri** (nume + rol) — vezi tabelul din secțiunea 1.

### Slide 5 — Impact
**Titlu:** Impact
**Lede:** "Nu doar arhitectură — un produs complet, de la cont curent până la credite."
**Cifre (doar cele cu substanță reală de business — fără commit-uri/linii de cod/oameni/zile):**
- 12 — servicii independente
- 18+ — reguli deterministe de fraudă
- 2 — agenți AI cu acțiuni reale
- 4 — produse dincolo de cont curent (credite, puncte, investiții, depozite)

**4 chip-uri:** Financial Guardian · WebAuthn/passkeys · Verificare ID cu DeepFace · Curs BNR live

### Slide 6 — Arhitectură — Microservicii
**Titlu:** Arhitectură — Microservicii
**Diagramă:** Angular → Nginx → API Gateway (JWT · rutare · rate limiting) → 12 servicii FastAPI, fiecare cu bază proprie MongoDB
**Listă "de ce" (lângă diagramă):**
- Angular + signals — stare locală simplă, potrivit pentru o echipă mică
- FastAPI — async nativ, viteză de dezvoltare
- MongoDB, o bază per serviciu — schemă flexibilă, fără migrări rigide
- Gateway — singura graniță de securitate

### Slide 7 — Financial Guardian
**Titlu:** Financial Guardian
**Flux în 3 pași:**
1. Motor determinist (18+ reguli fixe) decide dacă blochează
2. Decizie luată — fără nicio implicare AI
3. LLM explică, separat, async — staff + client, niciodată nu decide

**Statement final:** "LLM-ul nu decide niciodată."

### Slide 8 — Demo
**Titlu:** Demo (fără listă de pași afișată — se trece direct în aplicație, live)
**Flux real (pentru prezentator, nu pe slide):** înregistrare → cont/card → transfer normal → transfer reținut de fraudă → întrebare către MaestroAgent → schimb valutar BNR live → (dacă rămâne timp) credite/puncte

### Slide 9 — Închidere
**Conținut:** un rând mare, cu același stil/gradient ca titlul de pe slide 1 → "Mulțumim" · dedesubt, mai mic → "Întrebări?"

---

## 4. Referință — ce există deja

Există deja un deck HTML funcțional (navigare cu tastatură/click, fullscreen), construit exact pe conținutul de mai sus, cu paleta din secțiunea 2. Dacă Claude Design pornește de la el ca referință vizuală (nu obligatoriu), poate fi util să știe:
- Layout: full-bleed, un slide = un ecran, titlu mare stânga-sus (sau centrat pe sliduri de tip titlu/închidere), conținut centrat vertical
- Cardurile (probleme, echipă, arhitectură "de ce") — fundal navy ridicat (`#142248`), colțuri rotunjite generoase (16-18px), fără gradient-uri interne
- Cifrele mari (slide Impact) — tipografie display, bold, `font-variant-numeric: tabular-nums`
- Chip-urile/etichetele — pastilă, fundal albastru foarte închis, text accent

Acest document e suficient de complet pentru ca Claude Design să (re)construiască prezentarea vizual de la zero, sau s-o extindă — fără să fie nevoie de context suplimentar din conversație.
