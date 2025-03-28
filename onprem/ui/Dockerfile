FROM python:3.9-slim

WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install additional UI dependencies
RUN pip install --no-cache-dir jinja2 aiofiles

# Create necessary directories
RUN mkdir -p static templates

# Copy application code
COPY onprem/ui/main.py .
COPY onprem/ui/templates/* templates/

# Create a placeholder file in static directory if it's empty
RUN touch static/.placeholder

# Expose port
EXPOSE 8080

# Start the UI service
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--reload", "--log-level", "debug"] 