# Credite personale — design

## Ce e

Un produs nou, `loans-service` (microserviciu propriu, ca Depozite/
Investiții/Puncte). Userul cere un credit (sumă + termen), MaestroBank
verifică eligibilitatea din istoricul real de venituri, aprobă sau respinge
determinist, iar la aprobare suma intră imediat în contul curent. Rata
lunară (principal+dobândă) se debitează AUTOMAT, în fiecare lună, din contul
curent — la fel ca scadența unui depozit. Plată anticipată posibilă oricând.

Pagină separată în meniu ("Credite"), nu tab în Conturi — suprafață
comparabilă cu Investițiile (cerere, listă credite active, scadențar, istoric
plăți, plată anticipată).

## Date reale vs politică proprie

- **Dobânda anuală** e un tabel FIX, politică proprie MaestroBank — la fel
  ca ratele de depozit, nu există un feed extern nici la băncile reale
  pentru rata unui credit de consum (e stabilită intern, pe bază de risc).
- **Rata lunară** se calculează cu formula STANDARD de amortizare (aceeași
  folosită de orice bancă/calculator de credit real) — nu o simplificare:
  `rată = P × r × (1+r)^n / ((1+r)^n − 1)`, unde `r` = dobânda lunară,
  `n` = numărul de rate.
- **Verificarea de eligibilitate** e reală, pe date reale ale userului —
  vezi mai jos — nu aprobare oarbă.

## Parametri (politică MaestroBank, documentați ca atare în cod)

- Sumă: minim 1.000 RON, maxim 50.000 RON.
- Termene: 12, 24, 36, 60 luni.
- Dobândă anuală: 12L → 9,5% · 24L → 10,5% · 36L → 11,5% · 60L → 12,5%.
- Doar RON (contul curent, deja existent la fiecare user).

## Eligibilitate

Venitul mediu lunar = suma tranzacțiilor cu `category="income"` din ultimele
90 de zile / 3 (istoric REAL, tras din transactions-service, nu inventat —
aceeași sursă/filozofie ca bufferul de siguranță din MaestroAssistent:
"regulă simplă, documentată, NU un algoritm sofisticat").

Rata lunară nouă + suma ratelor lunare de la creditele deja active ale
userului NU poate depăși 40% din venitul mediu lunar (prag DTI simplu,
politică MaestroBank). Fără istoric de venit (0 tranzacții "income" în
fereastră) → cerere respinsă explicit, nu împărțire la zero.

Respins → mesaj clar, cu cifrele reale (ca la `render_recommendation` din
affordability_service), nu un refuz sec.

## Plată lunară automată

Scheduler (poll simplu, ca `maturity_loop` la Depozite): pentru fiecare
credit activ cu `next_payment_due_at <= acum`, încearcă debitarea ratei din
contul curent.
- Succes: se împarte rata în dobândă/principal (dobânda pe soldul rămas,
  restul e principal), se scade principalul rămas, se avansează scadența cu
  ~30 zile, se salvează o intrare în `loan_payments` (istoric, ca la
  ledger-ul de puncte).
- Ultima rată din scadențar închide exact soldul rămas (nu suma fixă a
  ratei), ca împrumutul să ajungă la 0 exact, nu cu rest din rotunjiri.
- Sold insuficient: NU se aplică nicio penalizare/dobândă de întârziere (ca
  la lichidarea depozitelor — regulă simplă, fără ramificații punitive) —
  doar reîncearcă la următorul ciclu, cu notificare către user.

## Plată anticipată

`POST /loans/{id}/payoff` — achită DOAR principalul rămas, fără dobândă
suplimentară pentru perioada parțială (simplificare documentată, în
avantajul clientului — la fel ca lichidarea unui depozit).

## Notificări noi

`loan_approved`, `loan_payment`, `loan_payment_missed`, `loan_paid_off` —
extind `NotificationKind` (support-service + frontend), la fel ca la Puncte.

## API (loans-service, prefix `/loans`, protejat integral)

- `GET /loans/rates`
- `POST /loans/apply` `{amount_minor, term_months}` → aprobat (LoanOut) sau
  422 cu motiv
- `GET /loans` — creditele userului
- `GET /loans/{id}/payments` — istoric plăți
- `POST /loans/{id}/payoff`

Reutilizează neschimbat: `accounts-service` (credit la aprobare, debit la
rată/payoff, by-user-and-type), `transactions-service`
(`/internal/transactions/by-user/{id}`, pull, ca la budgets-service),
`support-service` (`/internal/notifications`).
