FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY token_manager.py .
COPY cloud/proxy/reverse_proxy.py .

CMD ["uvicorn", "reverse_proxy:app", "--host", "0.0.0.0", "--port", "8001", "--reload", "--log-level", "debug"] 