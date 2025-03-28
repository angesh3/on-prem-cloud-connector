FROM python:3.9-slim

WORKDIR /app

COPY onprem/connector/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY onprem/connector/agent.py .

CMD ["python", "agent.py"] 