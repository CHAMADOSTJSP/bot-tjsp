FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

# Evita que pacotes tentem iniciar/registrar serviços durante o build
# (causa comum de falha no builder sandboxed do Render).
RUN mkdir -p /usr/sbin && printf '#!/bin/sh\nexit 0\n' > /usr/sbin/policy-rc.d \
    && chmod +x /usr/sbin/policy-rc.d

# Dependências mínimas do Chrome headless — SEM puxar recomendados
# (é isso que trazia systemd/dbus/pam/fontconfig e derrubava o build).
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    ca-certificates \
    fonts-liberation \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    && rm -rf /var/lib/apt/lists/*

# Instala o Chrome a partir do pacote .deb direto (não do repositório completo),
# com --no-install-recommends, para manter a árvore de dependências mínima.
RUN wget -q -O /tmp/chrome.deb \
    https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update \
    && apt-get install -y --no-install-recommends /tmp/chrome.deb \
    && rm -f /tmp/chrome.deb \
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
