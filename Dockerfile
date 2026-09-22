FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends arp-scan gosu iproute2 iputils-ping libcap2-bin \
    && setcap cap_net_raw+p /usr/sbin/arp-scan \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app.py ./
COPY auth.py ./
COPY version.json ./
COPY static/ ./static/
COPY docker-entrypoint.sh /usr/local/bin/wakeboard-entrypoint
RUN sed -i 's/\r$//' /usr/local/bin/wakeboard-entrypoint \
    && chmod +x /usr/local/bin/wakeboard-entrypoint

ENTRYPOINT ["/usr/local/bin/wakeboard-entrypoint"]
CMD ["python3", "app.py"]
