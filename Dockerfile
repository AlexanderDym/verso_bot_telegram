# Используем базовый образ Python
FROM python:3.9-slim

# Устанавливаем ffmpeg
RUN apt-get update && apt-get install -y ffmpeg

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем все файлы в контейнер
COPY . /app

# Устанавливаем зависимости
RUN pip install -r requirements.txt

# Команда для запуска бота
CMD ["python", "main.py"]
