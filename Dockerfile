FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# 1. Instalar dependências básicas do sistema e pacotes do Chrome
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    fonts-liberation \
    libnss3 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libxss1 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# 2. Instalar o Google Chrome oficial
RUN mkdir -p /etc/apt/keyrings \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /etc/apt/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 3. Copia primeiro o requirements.txt para utilizar o cache das camadas do Docker
COPY requirements.txt /app/

# 4. Instala dependências Python
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 5. Copia o código do projeto
COPY . /app

CMD ["python", "main.py"]