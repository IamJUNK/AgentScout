FROM python:3.12.12-slim-bookworm
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 AGENTSCOUT_NO_DOTENV=1
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
ARG INSTALL_LOCAL_EMBEDDINGS=0
COPY requirements-embedding.txt ./
RUN if [ "$INSTALL_LOCAL_EMBEDDINGS" = "1" ]; then pip install --no-cache-dir -r requirements-embedding.txt; fi
COPY . .
RUN useradd --create-home --uid 10001 agentscout && chown -R agentscout:agentscout /app
USER agentscout
CMD ["uvicorn", "app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
