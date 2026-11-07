# Build from the repository root (the ML package and A05 registry live outside backend/):
#   docker build -f backend/Dockerfile -t fairrent-api .                      # API image (default target)
#   docker build -f backend/Dockerfile --target verify -t fairrent-api-verify .   # B07 verification
FROM python:3.10-slim AS base

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
COPY ml/requirements.txt ml/requirements-inference.txt ./ml/
RUN pip install --no-cache-dir -r requirements.txt -r ml/requirements-inference.txt

COPY backend/*.py ./
COPY backend/sql/ ./sql/

# B07 inference runtime: only the modules ml.inference imports, plus the A05 geography registry (no database code).
COPY ml/inference.py ml/intervals.py ml/ontology_rules.py ml/attributions.py ml/train_compare.py ml/baseline.py ml/market_stats.py ml/verify_package.py ./ml/
COPY ml/examples/ ./ml/examples/
COPY data_pipeline/__init__.py data_pipeline/geography.py ./data_pipeline/
COPY contracts/openapi.json ./contracts/openapi.json
COPY contracts/openapi.json /contracts/openapi.json
COPY infra/valuation-coverage/coverage.geojson infra/valuation-coverage/districts.geojson ./valuation-coverage/
ENV VALUATION_COVERAGE_FILE=/app/valuation-coverage/coverage.geojson VALUATION_DISTRICTS_FILE=/app/valuation-coverage/districts.geojson

# Verification target: loads a mounted package and runs the example assessments inside the backend image.
#   docker run --rm -v "<abs path to artifacts/b07/VERSION>:/package:ro" fairrent-api-verify
FROM base AS verify
RUN pip install --no-cache-dir "jsonschema>=4.20"
ENV FAIRRENT_MODEL_PACKAGE=/package PYTHONDONTWRITEBYTECODE=1
CMD ["python", "-m", "ml.verify_package"]

# Last stage = default build target.
FROM base AS api
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
