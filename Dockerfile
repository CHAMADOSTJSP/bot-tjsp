FROM python:3.11-slim

# Dependências do sistema + Google Chrome estável
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    fonts-liberation \
    libnss3 \
    libxss1 \
    libappindicator3-1 \
    libasound2 \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Selenium Manager (embutido no selenium>=4.6) baixa o Chromedriver
# compatível automaticamente, então não fixamos versão manualmente.
ENV CHROME_BIN=/usr/bin/google-chrome

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY Automacao7_3_render.py .

# Render Background Worker: sem porta HTTP necessária.
CMD ["python", "Automacao7_3_render.py"]
