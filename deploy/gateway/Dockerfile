FROM python:3.11-slim

WORKDIR /app

COPY deploy/gateway/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY gateway_server.py /app/gateway_server.py

EXPOSE 18743

CMD ["sh", "-c", "uvicorn gateway_server:app --host ${GATEWAY_HOST:-0.0.0.0} --port ${GATEWAY_PORT:-18743}"]
