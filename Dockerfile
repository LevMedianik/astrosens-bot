FROM python:3.11-slim

# Системные пакеты
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "bot.py"]
