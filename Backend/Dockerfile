# Backend image - FastAPI + PyMySQL, no ORM (same app as `uvicorn main:app`
# run locally, see README.md). Built from Backend/ as the build context.
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first so this layer is cached across rebuilds unless
# requirements.txt actually changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# --reload matches local dev (uvicorn main:app --reload --port 8000); the
# compose file bind-mounts Backend/ over this image so edits on the host
# still hot-reload the container, same as running it natively.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
