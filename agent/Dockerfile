# Self-healing agent image. Build from REPO ROOT: docker build -f agent/Dockerfile -t healing-agent:v1 .
FROM python:3.12-slim
WORKDIR /app
ENV HOME=/app PYTHONPATH=/app/src PYTHONUNBUFFERED=1 \
    RUNBOOK_DIR=/app/runbooks CHROMA_DIR=/tmp/chroma
COPY agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Bake the embedding model INTO the image (no 80 MB download every time the pod starts)
RUN python -c "from chromadb.utils import embedding_functions as ef; ef.DefaultEmbeddingFunction()(['warm up'])"
COPY agent/src ./src
COPY runbooks ./runbooks
RUN useradd -u 10001 agent && chown -R agent /app
USER 10001
EXPOSE 8085
CMD ["python", "-m", "healer.server"]
