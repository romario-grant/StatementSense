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

# Cloud Run sets the PORT env var — default to 8080
ENV PORT=8080

EXPOSE 8080

# Use standard python execution with shell expansion for $PORT
CMD ["sh", "-c", "python -m uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
