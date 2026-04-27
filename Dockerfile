FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/main.py .

# Create data directory
RUN mkdir -p /root/.ninja-data

EXPOSE 3030

CMD ["python", "main.py"]
