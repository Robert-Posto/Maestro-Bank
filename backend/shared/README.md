# shared/

Rezervat pentru cod comun mai multor microservicii (ex. modele de bază,
utilitare comune), pentru o etapă ulterioară.

Momentan fiecare serviciu are propriile module `database.py` / `config.py`
/ `models.py`, duplicate intenționat — fiecare serviciu are propriul
context de build Docker (`context: ./backend/services/<service>`), izolat
de restul. Introducerea unui pachet Python comun ar necesita schimbarea
contextului de build (ex. la `./backend`) și ajustarea fiecărui
`Dockerfile` — o schimbare structurală care nu e necesară încă la acest
nivel de complexitate.
