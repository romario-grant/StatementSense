# ═══════════════════════════════════════════════════════════
# StatementSense — FastAPI Backend Dockerfile
# For deployment to Google Cloud Run
# ═══════════════════════════════════════════════════════════

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for pdfplumber (which uses pdfminer)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source code
COPY backend/ ./backend/

# Copy engine source files (referenced by backend)
COPY RenewalSense.py .
COPY ScreentimeSense.py .
COPY CalendarSense.py .
COPY Screentime.py .

# Copy ML models
COPY models/ ./models/

# The GEMINI_API_KEY is injected at runtime via Secret Manager
# (configured in Cloud Run service settings)

# Cloud Run sets PORT env var — uvicorn listens on it
ENV PORT=8080

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8080"]
