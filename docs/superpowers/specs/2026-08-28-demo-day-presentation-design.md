# MaestroBank — Demo Day Presentation Design

**Goal:** A 20-30 minute business-oriented presentation (demo included) for AI Academy's demo day, presented solo by Robert, audience = mentors + program managers. Focus: what was built and what would come next — not a "what we learned" retrospective.

**Format:** Both — an editable HTML/Artifact deck, and this plan as content for a Slidesgo template.

**Narrative technique borrowed from the LinkedIn Series B deck (reidhoffman.org/linkedin-pitch-to-greylock):** lead with the thesis before data; address the audience's obvious skepticism ("is this just a school project?") early and directly, not defensively; use analogies to things the audience already trusts (Revolut/N26-style apps); show don't tell (real numbers, real screenshots, a real running system); close on the same thesis the deck opened with.

**Revision 2 (copy-editing + layout pass):** applied the Seven Sweeps to cut "vanity-flex" phrasing (commit counts, line counts, team size/timeline framed as an achievement — e.g. "4 oameni, 10 zile") in favor of numbers that carry real business signal (service count, fraud-rule depth, product breadth). Also: unified every slide onto a single, larger title (dropped the small uppercase eyebrow label + its underline rule), cut the "Pași spre producție" slide entirely (kept as Q&A backup, not presented), and rewrote the closing slide down to two lines.

**Total estimated time:** ~21-24 minutes (fits the 20-30 min budget, with room to spare).

---

## Structure overview

| # | Section | Time |
|---|---------|------|
| 1 | Deschidere | 1 min |
| 2 | Problema | 2 min |
| 3 | Poziționare | 1.5-2 min |
| 4 | Echipa | 1.5 min |
| 5 | Impact | 2 min |
| 6 | Arhitectură — Microservicii | 4-5 min |
| 7 | Financial Guardian | (parte din 6, sau slide separat) |
| 8 | Demo | 8-10 min |
| 9 | Închidere | 1 min |

---

## 1. Deschidere (1 min)

**Pe slide:** doar "MaestroBank" — mare, centrat, nimic altceva (fără subtitlu, fără eyebrow).

**Ce spui:**
> "Bună ziua. În următoarele 25 de minute o să vă arăt ce am construit — nu o interfață care doar arată bine, ci un sistem bancar complet funcțional: 12 microservicii, un motor de detecție a fraudei, doi agenți AI care chiar acționează asupra contului tău, și integrare reală cu cursul valutar oficial al BNR. Se numește MaestroBank, și rulează chiar acum, live — o să v-o arăt la final."

**Notă de design:** ultima propoziție ("rulează chiar acum, live") plantează promisiunea demo-ului de la final — parte din tehnica "închide unde ai deschis."

---

## 2. Problema (2 min)

**Pe slide — titlu:** Problema

**4 carduri (fără nicio propoziție introductivă deasupra):**
- Fraudă detectată ȘI explicată — nu doar blocată orbește
- Asistență care acționează, nu doar răspunde la FAQ
- Autentificare modernă, fără parole slabe/refolosite
- Date reale, nu simulate

**Ce spui:**
> "Patru probleme reale. Una: o bancă care blochează o tranzacție dar nu-ți spune de ce — pe tine te enervează, pe personalul din spate îl încetinește. Doi: majoritatea 'asistenților AI' din bănci răspund la întrebări, dar nu pot chiar să facă ceva pentru tine — la noi, agentul poate propune o modificare de buget sau un tichet de suport, tu doar confirmi. Trei: parolele sunt punctul cel mai slab din orice sistem — noi am pus autentificare fără parolă, cu passkey. Patru: multe demo-uri simulează datele — la noi cursul valutar e cel oficial, live, de la BNR."

---

## 3. Poziționare (1.5-2 min)

**Pe slide — titlu:** Poziționare

**Statement mare, sub titlu:** "Nu doar o aplicație. Un core bancar modular."

**Vizual:** 12 blocuri mici → săgeată → eticheta "banking-as-a-service"

**Ce spui:**
> "Un lucru care ne diferențiază: n-am construit o aplicație monolitică de bancă, am construit un CORE bancar modular. Motorul de fraudă, agenții AI, autentificarea, conturile — fiecare e un serviciu independent, cu API propriu, izolat. Practic, orice bucată din ce vedeți poate fi luată separat și oferită altei companii fintech ca infrastructură — genul de arhitectură pe care o folosesc jucători reali din banking-as-a-service. Nu e doar o alegere tehnică — e o poziționare: nu suntem doar un produs, suntem o fundație pe care se poate construi."

**Notă de design:** se leagă direct de secțiunea 6 (arhitectură) — aici afirmi, acolo demonstrezi tehnic.

---

## 4. Echipa (1.5 min)

**Pe slide — titlu:** Echipa

**4 carduri, nume + rol:**

| Nume | Rol |
|------|-----|
| **Robert** | Arhitectură & orchestrare (Gateway, cum se leagă toate serviciile) + verificare de identitate (DeepFace, ID + selfie) |
| **Octavia** | Agenți AI (MaestroAgent + Support Agent, unificați ulterior într-un singur asistent) + Investiții + Credite + Puncte de loialitate |
| **Calin** | Nucleu bancar + reguli de securitate/fraudă + Financial Guardian + autentificare passkey + eSign + traduceri RO/EN |
| **Alex** | Testare + remediere bug-uri + polish frontend |

**Ce spui:**
> "Fiecare a avut o zonă clară de responsabilitate, dar am lucrat des peste granițe."

---

## 5. Impact (2 min)

**Pe slide — titlu:** Impact

**Lede scurt:** "Nu doar arhitectură — un produs complet, de la cont curent până la credite."

**Grid de cifre — doar cele cu substanță reală de business, fără flex de efort (commit-uri/linii de cod/oameni/zile — tăiate):**

- **12** servicii independente
- **18+** reguli deterministe de fraudă
- **2** agenți AI cu acțiuni reale
- **4** produse dincolo de cont curent — credite, puncte, investiții, depozite

**Sub cifre — 4 highlight-uri scurte:** Financial Guardian · WebAuthn/passkeys · Verificare ID cu DeepFace · Curs valutar BNR live

**Ce spui:**
> "Dincolo de interfață, câteva lucruri arată profunzimea reală: 12 servicii independente, un motor de fraudă cu peste 18 reguli deterministe, doi agenți AI care nu doar răspund — acționează direct asupra contului tău — și patru produse complete dincolo de contul curent: credite, puncte de loialitate, investiții, depozite. Patru capabilități concrete confirmă calitatea, nu doar volumul: motorul de fraudă cu explicații AI, autentificare fără parolă, verificare biometrică de identitate, și curs valutar oficial, live."

---

## 6. Arhitectură — Microservicii (4-5 min)

**Pe slide — titlu:** Arhitectură — Microservicii

**Diagramă:** Angular → Nginx → API Gateway → cele 12 microservicii → MongoDB (o bază per serviciu).

**Ce spui (alegeri, cu "de ce", nu doar "ce"):**
> - "Angular 22, cu signals — stare locală simplă, fără un store RxJS greoi. Potrivit pentru o echipă mică, unde viteza de dezvoltare contează mai mult decât un pattern de enterprise la scară mare."
> - "FastAPI — async nativ, tipare stricte cu Pydantic, viteză mare de dezvoltare. Ne-a lăsat să scriem servicii izolate rapid, fără cod boilerplate."
> - "MongoDB, o bază separată per serviciu — schemă flexibilă, fără migrări SQL rigide, exact ce ai nevoie când modelul de date se schimbă des, în dezvoltare rapidă, cu mai mulți oameni care ating cod în paralel."
> - "API Gateway — singura graniță de securitate. Validează JWT-ul o dată, rutează către serviciul corect, blochează explicit orice rută internă să fie atinsă din browser."
> - "Docker Compose — fiecare serviciu se buildează și se testează independent. Ăsta a fost motorul real al lucrului în paralel — vezi slide-ul de poziționare: arhitectura asta NU e doar o alegere tehnică, e ce ne-a permis să livrăm atât de mult."

---

## 7. Financial Guardian (parte din cele 4-5 min de mai sus, sau slide separat)

**Pe slide — titlu:** Financial Guardian

**Flux în 3 pași:**
1. Motor determinist (18+ reguli fixe) decide dacă blochează o tranzacție
2. Separat, async, un LLM DOAR explică decizia deja luată — staff + client
3. LLM-ul nu decide NICIODATĂ

**Ce spui:**
> "Un exemplu concret de gândire de inginerie, nu doar 'am pus AI peste tot': motorul de fraudă e 100% determinist — 18 reguli fixe, testabile, previzibile. Când o tranzacție e reținută, un LLM separat, asincron, generează O EXPLICAȚIE în limbaj natural — pentru personalul băncii ȘI pentru client — dar niciodată nu participă la decizie. Separarea asta e deliberată: nu vrei ca un model de limbaj să poată fi convins să lase o fraudă să treacă."

---

## 8. Demo (8-10 min, la final)

**Pe slide — titlu:** Demo (fără lista de pași afișată — treci direct în aplicație)

**Flux ghidat, ca reper propriu:**

1. Înregistrare → provisioning automat de cont + card demo
2. Prezentare cont/card
3. Un transfer normal, reușit
4. Un transfer care declanșează hold de fraudă → arăți explicația Financial Guardian
5. Întrebare către MaestroAgent → propune o ajustare de buget, tu confirmi
6. Schimb valutar cu curs BNR live
7. (dacă rămâne timp) Credite sau Puncte de loialitate

**Notă:** acesta e locul unde teza de deschidere ("rulează chiar acum, live") se demonstrează literal — nu doar spui, arăți.

---

## 9. Închidere (1 min)

**Pe slide:** un rând mare, cu același gradient ca "MaestroBank" de pe slide-ul 1 → "Mulțumim" · dedesubt, mai mic → "Întrebări?"

**Ce spui:**
> "Am pornit de la ideea să construim o bancă digitală funcțională, nu un mockup — și un core bancar modular, nu doar un produs. Ați văzut-o rulând, live, chiar acum. Mulțumim — suntem aici pentru întrebări."

---

## Rezervă pentru Q&A (nu e pe slide)

"Pași spre producție" a fost eliminat ca slide dedicat, dar merită un răspuns pregătit dacă vine întrebarea:

- Replica set MongoDB → tranzacții atomice reale (nu debit+credit condițional cu rollback manual)
- Integrare reală Visa/Mastercard/SEPA/PSD2
- Compliance/KYC/AML real, dincolo de verificarea demo de identitate
- Coadă de mesaje reală (RabbitMQ) în loc de bucle asyncio in-process
- Rate limiting distribuit (Redis) pentru scalare orizontală
- Cookies httpOnly + refresh tokens, în loc de JWT în sessionStorage

---

## Status: aprobat

Livrabile publicate (Artifacts, actualizate la aceleași URL-uri):
1. Deck HTML editabil.
2. Document de conținut curat, gata de copiat într-un template Slidesgo (include și rezerva de Q&A de mai sus).
