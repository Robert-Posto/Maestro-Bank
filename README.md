# MaestroBank

Schelet inițial de proiect pentru MaestroBank — aplicație bancară demo.

## Arhitectură

| Componentă | Tehnologie          | Port  |
| ---------- | -------------------- | ----- |
| Frontend   | Angular               | 4200  |
| Backend    | FastAPI (Python)      | 8000  |
| Database   | MongoDB               | 27017 |

Cele trei servicii rulează în containere Docker separate, conectate prin aceeași rețea Docker Compose. Backendul se conectează la MongoDB folosind hostname-ul `mongodb` (numele serviciului din Docker Compose), nu `localhost`.

## Cum pornesc proiectul

```bash
docker compose up --build
```

Prima pornire durează mai mult (instalare dependențe Angular și Python). Pornirile ulterioare sunt mai rapide.

## Cum îl opresc

```bash
docker compose down
```

## URL-uri

- Frontend (Angular): http://localhost:4200
- Backend (FastAPI): http://localhost:8000
- Swagger / documentație API: http://localhost:8000/docs
- MongoDB: `mongodb://localhost:27017` (din host) / `mongodb://mongodb:27017` (din alte containere)

## Stare curentă

Acesta este doar scheletul de infrastructură — fără logică de business, autentificare sau modele bancare. Fiecare componentă conține doar aplicația minimă necesară pentru a porni și a răspunde la un health check.
