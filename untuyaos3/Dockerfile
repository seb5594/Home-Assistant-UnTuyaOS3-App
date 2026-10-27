# syntax=docker/dockerfile:1
ARG BUILD_FROM=python:3.13-slim-trixie@sha256:d3449c0493345868b09708d7056dce5edda3a75233ea86008fc80c934d355a10
FROM ${BUILD_FROM} AS build
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ARG UNTUYAOS3_COMMIT=2111458225c269ddddf5353bf09a1e8f1096d959
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl build-essential libssl-dev \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir /upstream && curl --fail --location --retry 3 \
    "https://codeload.github.com/tuya-cloudcutter/UnTuyaOS3/tar.gz/${UNTUYAOS3_COMMIT}" \
    | tar -xz --strip-components=1 -C /upstream \
    && printf '%s\n' "$UNTUYAOS3_COMMIT" > /upstream/UPSTREAM_COMMIT
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir \
    pycryptodome==3.23.0 py-datastruct==2.0.0 sslpsk3==2.1.0
COPY integration/patch_upstream.py /tmp/patch_upstream.py
RUN python /tmp/patch_upstream.py /upstream

FROM ${BUILD_FROM}
ARG BUILD_VERSION=0.1.1-beta.3
ARG BUILD_ARCH=amd64
RUN apt-get update && apt-get install -y --no-install-recommends bash iw iproute2 udhcpc tini \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /opt/venv /opt/venv
COPY --from=build /upstream /opt/untuyaos3
COPY app/ /opt/webapp/
COPY integration/dhcp.sh /opt/webapp/dhcp.sh
COPY run.sh /run.sh
RUN chmod 755 /opt/webapp/dhcp.sh /run.sh
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UNTUYAOS3_SKIP_INSTALL=1
WORKDIR /opt/webapp
LABEL io.hass.name="UnTuyaOS3" io.hass.description="Interactive UnTuyaOS3 with Ingress and live logs" \
    io.hass.type="addon" io.hass.version="${BUILD_VERSION}" io.hass.arch="${BUILD_ARCH}" \
    org.opencontainers.image.source="https://github.com/seb5594/Home-Assistant-UnTuyaOS3-App"
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/run.sh"]
