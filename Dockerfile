FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY oracle/ ./oracle
COPY dashboard/ ./dashboard

RUN mkdir -p /data

ENV PORT=7860
EXPOSE 7860

CMD ["python", "-m", "uvicorn", "oracle.main:app", "--host", "0.0.0.0", "--port", "7860"]
