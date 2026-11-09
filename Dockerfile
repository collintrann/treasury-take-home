FROM python:3.13-slim

# Tesseract powers the offline OCR fallback.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY samples ./samples

ENV PYTHONUNBUFFERED=1 OMP_THREAD_LIMIT=1
EXPOSE 8000
# Most hosts (Render, Railway, Azure App Service, Cloud Run) inject $PORT.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
