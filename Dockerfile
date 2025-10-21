FROM ubuntu:22.04

# Evitar preguntas interactivas
ENV DEBIAN_FRONTEND=noninteractive

# Instala dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    apt-transport-https python3 python3-venv python3-pip ca-certificates curl gnupg2 wget unzip xvfb \
    fonts-liberation libnss3 libxss1 libasound2 libatk-bridge2.0-0 libgtk-3-0 libx11-xcb1 \
    && rm -rf /var/lib/apt/lists/*

# Instala Google Chrome (estándar estable)
RUN wget -q -O /tmp/google-chrome-stable_current_amd64.deb \
    https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update && apt-get install -y --no-install-recommends /tmp/google-chrome-stable_current_amd64.deb \
    && rm -f /tmp/google-chrome-stable_current_amd64.deb \
    || true

# Crea directorio de trabajo
WORKDIR /app

# Copia requirements y código
COPY requirements.txt /app/requirements.txt
# Copia explícita del archivo .env si existe en el contexto de build
COPY .env /app/.env
COPY . /app

# Instala dependencias Python
RUN python3 -m pip install --upgrade pip setuptools wheel \
    && pip install -r /app/requirements.txt

ENV PYTHONUNBUFFERED=1

# Puerto o variables por defecto (si las usa el proyecto)
ENV NTFY_URL="https://ntfy.sh"

# Ejecuta el script principal por defecto
CMD ["python3", "visa_reprogram.py"]
