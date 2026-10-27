ARG BUILD_FROM=@@BASE_IMAGE@@
FROM ${BUILD_FROM}
ARG BUILD_VERSION=@@VERSION@@
ARG BUILD_ARCH=amd64
RUN apk add --no-cache @@RUNTIME_PACKAGES@@
COPY app/ /opt/helper/
COPY run.sh /run.sh
RUN chmod 755 /run.sh
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /opt/helper
LABEL io.hass.name="UnTuyaOS3 Wi-Fi Helper" io.hass.description="Dedicated radio namespace broker" \
    io.hass.type="addon" io.hass.version="${BUILD_VERSION}" io.hass.arch="${BUILD_ARCH}" \
    org.opencontainers.image.source="https://github.com/seb5594/Home-Assistant-UnTuyaOS3-App"
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["/run.sh"]
