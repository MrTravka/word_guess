FROM node:24-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim-bookworm AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////data/word_guess.db
WORKDIR /app
COPY backend/requirements.lock /app/backend/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /app/backend/requirements.lock
COPY backend/ /app/backend/
COPY scripts/verify_content.py scripts/fetch_content.py scripts/prepare_definitions.py /app/scripts/
COPY data/words/ /app/data/words/
COPY data/definitions/ /app/data/definitions/
COPY data/licenses/ /app/data/licenses/
COPY data/audio/ /app/data/audio/
COPY ost.mp3 THIRD_PARTY_NOTICES.md /app/
RUN python scripts/verify_content.py --require-target
COPY --from=frontend /build/frontend/dist /app/frontend/dist
RUN mkdir -p /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
CMD ["python", "-m", "backend.app.container_start"]
