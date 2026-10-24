FROM python:3.12-slim

# ------------------------------------------------------------------------------
# System dependencies.
# `curl` is kept for healthchecks/debugging. `nmap` is installed by default
# since it's a lightweight, commonly-packaged CLI tool and is safe to have
# present even when SCANNER_MODE=mock (it simply won't be invoked).
#
# Nuclei is NOT installed by default (it requires a Go-built binary download).
# To enable REAL scanner mode with Nuclei, uncomment the block below or
# mount a pre-built `nuclei` binary into the container at
# /usr/local/bin/nuclei (matching NUCLEI_BINARY_PATH in .env).
# ------------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    nmap \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Uncomment to install Nuclei for REAL scanner mode:
# RUN curl -sSL https://github.com/projectdiscovery/nuclei/releases/latest/download/nuclei_linux_amd64.zip \
#     -o /tmp/nuclei.zip \
#     && unzip /tmp/nuclei.zip -d /usr/local/bin \
#     && rm /tmp/nuclei.zip \
#     && chmod +x /usr/local/bin/nuclei

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]