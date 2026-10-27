FROM python:3.13-slim-trixie
RUN apt-get update && apt-get install -y --no-install-recommends iw iproute2 systemd tini \
    && rm -rf /var/lib/apt/lists/*
COPY app/ /opt/helper/
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /opt/helper
LABEL io.hass.name="UnTuyaOS3 Wi-Fi Helper" io.hass.description="Dedicated radio namespace broker" \
    io.hass.type="addon" io.hass.version="0.1.0"
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "/opt/helper/broker.py"]
