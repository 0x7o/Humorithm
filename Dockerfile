FROM python:3.9

RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libglib2.0-0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Создаем директорию для хранения данных
RUN mkdir -p /app/data

# Устанавливаем права на запись в директорию
RUN chmod -R 777 /app/data

# По умолчанию запускаем Flask приложение, но это может быть переопределено в docker-compose
CMD ["python", "model.py"]
