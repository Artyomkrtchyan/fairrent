FROM python:3.10-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/*.py ./
COPY backend/sql/ ./sql/
COPY ml/baseline.py /app/ml/baseline.py
COPY contracts/openapi.json /contracts/openapi.json

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
