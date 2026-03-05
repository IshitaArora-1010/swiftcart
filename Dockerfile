FROM python:3.12-slim

WORKDIR /app

# Install Python dependencies first (separate layer so they are cached between builds)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the source code
COPY . .

EXPOSE 8000

# Run with uvicorn — host 0.0.0.0 makes the server reachable outside the container
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
