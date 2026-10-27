ARG BUILD_FROM=python:3.13-slim-trixie@sha256:d3449c0493345868b09708d7056dce5edda3a75233ea86008fc80c934d355a10
FROM ${BUILD_FROM}
ARG BUILD_VERSION=0.1.1-beta.5
ARG BUILD_ARCH=amd64
RUN apt-get update && apt-get install -y --no-install-recommends iw iproute2 systemd tini \
    && rm -rf /var/lib/apt/lists/*
COPY app/ /opt/helper/
COPY run.sh /run.sh
RUN chmod 755 /run.sh
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /opt/helper
LABEL io.hass.name="UnTuyaOS3 Wi-Fi Helper" io.hass.description="Dedicated radio namespace broker" \
    io.hass.type="addon" io.hass.version="${BUILD_VERSION}" io.hass.arch="${BUILD_ARCH}" \
    org.opencontainers.image.source="https://github.com/seb5594/Home-Assistant-UnTuyaOS3-App"
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/run.sh"]
