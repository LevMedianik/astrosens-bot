FROM python:3.11-slim

# Установим зависимости системы
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /app

# Копируем файлы проекта
COPY . .

# Установим зависимости Python
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "bot.py"]
