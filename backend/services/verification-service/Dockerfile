FROM python:3.12-slim

WORKDIR /app

# opencv (folosit de DeepFace pentru detecția feței) cere aceste librării
# de sistem, absente pe imaginea slim — fără ele, importul cv2 pică cu
# "libGL.so.1: cannot open shared object file".
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Instalare grea (DeepFace -> TensorFlow) — build-ul acestei imagini
# durează semnificativ mai mult decât la celelalte microservicii; e
# normal, se întâmplă o singură dată (layer cache-uit după primul build).
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
