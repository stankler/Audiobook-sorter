FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
# Install CPU-only torch first to avoid pulling 2GB+ of CUDA libraries
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./
COPY pipeline/ ./pipeline/
COPY stt/ ./stt/
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7171", "--log-level", "info"]
