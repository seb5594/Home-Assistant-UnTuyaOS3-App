ARG BUILD_FROM=ghcr.io/home-assistant/base:3.24-2026.10.0

# renovate: datasource=repology depName=alpine_3_24/jq
ARG JQ_VERSION=1.8.2-r0
# renovate: datasource=repology depName=alpine_3_22/jq
ARG JQ_VERSION_LEGACY=1.8.2-r0

FROM ${BUILD_FROM}

ARG JQ_VERSION
RUN apk add --no-cache jq=${JQ_VERSION}

ARG BUILD_VERSION=0.1.0
ARG BUILD_ARCH=amd64
LABEL io.hass.version="${BUILD_VERSION}" \
    io.hass.type="addon" \
    io.hass.arch="${BUILD_ARCH}" \
    org.opencontainers.image.source="https://github.com/seb5594/Home-Assistant-App-Template"

COPY run.sh entrypoint.sh /
RUN chmod a+x /run.sh /entrypoint.sh

ENTRYPOINT [ "/bin/bash", "/entrypoint.sh" ]
CMD [ "/run.sh" ]
