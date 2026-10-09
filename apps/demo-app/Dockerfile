FROM python:3.12-slim
WORKDIR /app
# Install dependencies first (cached layer: only reruns when requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
# Run as non-root (security best practice)
RUN useradd -u 10001 appuser
USER 10001
EXPOSE 8080
CMD ["python", "app.py"]
