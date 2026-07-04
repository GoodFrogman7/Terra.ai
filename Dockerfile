FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/ apps/
COPY core/ core/
COPY config/ config/
COPY data/kb_finance/ data/kb_finance/
COPY data/kb_healthcare/ data/kb_healthcare/

# Indexes rebuild automatically on first query; memory/analytics DBs live on a volume
EXPOSE 8000 8501

# Default command runs the API; the UI service overrides this in docker-compose
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
