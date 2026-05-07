FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/

# Run Alembic migrations before starting the server.
# In production, prefer running migrations in a separate init container
# or via scripts/migrate.sh to avoid blocking the app start.

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
