FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py model_stub.py listing_models.py listing_repository.py listing_routes.py source_adapter.py sync_listings.py ./
COPY sql/ ./sql/

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
