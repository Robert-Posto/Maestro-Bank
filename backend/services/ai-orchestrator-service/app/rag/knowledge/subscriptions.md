# Abonamente și plăți recurente

## De ce sunt tratate separat de cheltuielile variabile

Abonamentele (Netflix, Spotify, facturi cu sumă fixă etc.) au o dată de
scadență cunoscută dinainte — nu trebuie estimate din ritmul mediu de
cheltuire, ca restul cumpărăturilor. De-aia le scădem separat din sold,
ca obligații fixe, nu ca parte din cheltuiala variabilă zilnică.

## Deja plătite vs. rămase de plată

Într-o lună, un abonament e "deja plătit" dacă ziua lui de facturare
(billing day) a trecut deja în luna curentă, și "rămas de plată" dacă
scadența e încă în față. Suma totală a abonamentelor active dintr-o lună
e mereu deja-plătite + rămase — niciun abonament nu dispare din calcul,
doar își schimbă starea pe parcursul lunii.

## Ce înseamnă un abonament "inactiv"

Un abonament dezactivat de user nu mai intră în niciun calcul de forecast
sau de plăți rămase — e ca și cum nu ar exista, chiar dacă a fost activ
în trecut.
