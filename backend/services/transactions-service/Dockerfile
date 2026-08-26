FROM python:3.12-slim

WORKDIR /app

# fonts-dejavu-core — Helvetica (fontul de bază din reportlab) nu are
# glife pentru diacriticele românești (ă, â, î, ș, ț — vezi app/statement.py,
# extrasul de cont PDF); DejaVu Sans le acoperă complet și e un pachet apt
# ușor (fără dependențe X11/GUI).
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
