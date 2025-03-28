FROM python:3.9-slim

WORKDIR /app

COPY cloud/ui/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p static templates
COPY cloud/ui/main.py .
COPY cloud/ui/templates/* templates/
RUN touch static/.placeholder

CMD ["python", "main.py"] 