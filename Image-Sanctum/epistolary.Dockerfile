FROM pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime

WORKDIR /librarius

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-epistolary.txt .
RUN pip install --no-cache-dir -r requirements-epistolary.txt

COPY epistolary.py .

ENTRYPOINT ["python", "epistolary.py"]
