FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    tar \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Stellar CLI precompiled binary robustly using find
RUN curl -sL https://github.com/stellar/stellar-cli/releases/download/v22.0.1/stellar-cli-22.0.1-x86_64-unknown-linux-gnu.tar.gz | tar -xz -C /tmp \
    && find /tmp -type f -name "stellar" -exec mv {} /usr/local/bin/stellar \; \
    && chmod +x /usr/local/bin/stellar \
    && rm -rf /tmp/*

WORKDIR /app

# Copy dependency requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application directories
COPY oracle/ ./oracle
COPY dashboard/ ./dashboard

# Configure environment port for Hugging Face Spaces (default 7860)
ENV PORT=7860
EXPOSE 7860

# Override backend STELLAR_CLI binary path for Linux container
ENV STELLAR_CLI_PATH=/usr/local/bin/stellar

CMD ["python", "-m", "uvicorn", "oracle.main:app", "--host", "0.0.0.0", "--port", "7860"]
