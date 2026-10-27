ARG BUILD_FROM=@@BASE_IMAGE@@
FROM ${BUILD_FROM} AS build
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ARG UNTUYAOS3_COMMIT=@@UPSTREAM_REVISION@@
RUN apk add --no-cache @@BUILD_PACKAGES@@
RUN mkdir /upstream && curl --fail --location --retry 3 \
    "https://codeload.github.com/tuya-cloudcutter/UnTuyaOS3/tar.gz/${UNTUYAOS3_COMMIT}" \
    | tar -xz --strip-components=1 -C /upstream \
    && printf '%s\n' "$UNTUYAOS3_COMMIT" > /upstream/UPSTREAM_COMMIT
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir @@PYTHON_PACKAGES@@
COPY integration/patch_upstream.py /tmp/patch_upstream.py
RUN python /tmp/patch_upstream.py /upstream

FROM ${BUILD_FROM}
ARG BUILD_VERSION=@@VERSION@@
ARG BUILD_ARCH=amd64
RUN apk add --no-cache @@RUNTIME_PACKAGES@@
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
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["/run.sh"]
