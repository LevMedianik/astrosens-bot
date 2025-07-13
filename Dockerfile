# Базовый имидж
FROM python:3.11-slim

# Устанавливаем зависимости системы для PyMuPDF и FAISS
RUN apt-get update && apt-get install -y \
    build-essential \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем только нужные файлы
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Копируем оставшийся код
COPY . .

# Указываем команду запуска
CMD ["python", "bot.py"]
