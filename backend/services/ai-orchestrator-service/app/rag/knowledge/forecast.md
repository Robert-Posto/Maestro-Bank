# Cum funcționează forecast-ul de sfârșit de lună

## Formula pe scurt

Soldul estimat la finalul lunii = soldul curent, minus cheltuielile
variabile estimate pentru zilele rămase din lună, minus obligațiile fixe
cunoscute care mai urmează (abonamente cu scadență în restul lunii).
Cheltuielile variabile estimate se calculează din ritmul mediu de
cheltuire zilnic al userului în luna curentă, înmulțit cu numărul de zile
rămase.

## De ce e doar o estimare

Forecast-ul presupune că userul continuă să cheltuiască în ritmul mediu
observat până acum în luna curentă. Nu ține cont de evenimente
neplanificate (o cheltuială mare bruscă) și nu modelează venituri
viitoare cu certitudine — nu e o predicție garantată, e o proiecție
bazată pe comportamentul recent real.

## Când forecast-ul e mai puțin precis

La începutul lunii, cu foarte puține tranzacții înregistrate, ritmul mediu
zilnic poate fi înșelător (o singură cheltuială mare distorsionează media).
Spre finalul lunii, cu mai mult istoric acumulat, estimarea devine de
obicei mai stabilă.
