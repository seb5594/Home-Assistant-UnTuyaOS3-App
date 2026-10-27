FROM python:3.13-slim-trixie@sha256:d3449c0493345868b09708d7056dce5edda3a75233ea86008fc80c934d355a10
RUN apt-get update && apt-get install -y --no-install-recommends iw iproute2 systemd tini \
    && rm -rf /var/lib/apt/lists/*
COPY app/ /opt/helper/
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /opt/helper
LABEL io.hass.name="UnTuyaOS3 Wi-Fi Helper" io.hass.description="Dedicated radio namespace broker" \
    io.hass.type="addon" io.hass.version="0.1.0"
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "/opt/helper/broker.py"]
