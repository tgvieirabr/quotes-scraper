FROM python:3.11-slim

WORKDIR /app

# Instalar dependências do sistema incluindo Chrome
RUN apt-get update && apt-get install -y \
    gcc \
    wget \
    gnupg \
    curl \
    unzip \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código da aplicação
COPY . .

# Criar diretórios necessários
RUN mkdir -p data logs screenshots

# Variáveis de ambiente
ENV PYTHONUNBUFFERED=1
ENV SELENIUM_GRID_URL=http://selenium-hub:4444

# Comando padrão
CMD ["python", "scraper.py"]