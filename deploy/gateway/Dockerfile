FROM tiangolo/uvicorn-gunicorn-fastapi:python3.11-slim

WORKDIR /app

COPY gateway_server.py /app/gateway_server.py

EXPOSE 18743

CMD ["sh", "-c", "uvicorn gateway_server:app --host ${GATEWAY_HOST:-0.0.0.0} --port ${GATEWAY_PORT:-18743}"]
