FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends arp-scan iproute2 iputils-ping libcap2-bin \
    && setcap cap_net_raw+p /usr/sbin/arp-scan \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app.py ./
COPY static/ ./static/

CMD ["python3", "app.py"]
