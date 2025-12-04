FROM python:3.11-slim

WORKDIR /librarius

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    tesseract-ocr \
    poppler-utils \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-lexicanium.txt .
RUN pip install --no-cache-dir -r requirements-lexicanium.txt

COPY lexicanium.py .

RUN mkdir -p /librarius/archive /librarius/Data-Slates

ENTRYPOINT ["python", "lexicanium.py"]
