ARG BUILD_FROM=@@BASE_IMAGE@@
FROM ${BUILD_FROM} AS build
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN apk add --no-cache @@BUILD_PACKAGES@@
RUN mkdir /upstream && curl --fail --location --retry 3 \
    https://codeload.github.com/@@UPSTREAM_REPOSITORY@@/tar.gz/@@UPSTREAM_REVISION@@ \
    | tar -xz --strip-components=1 -C /upstream \
    && printf '%s\n' @@UPSTREAM_REVISION@@ > /upstream/UPSTREAM_COMMIT
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir @@PYTHON_PACKAGES@@
COPY integration/patch_upstream.py /tmp/patch_upstream.py
RUN python /tmp/patch_upstream.py /upstream
RUN mkdir /cloudcutter && curl --fail --location --retry 3 \
    https://codeload.github.com/@@CLOUDCUTTER_REPOSITORY@@/tar.gz/@@CLOUDCUTTER_REVISION@@ \
    | tar -xz --strip-components=1 -C /cloudcutter
# Separate virtual environments preserve UnTuyaOS3's sslpsk3 2.x and CloudCutter's
# byte-preserving 1.1.1 callbacks. Both use the official HA Python 3.13 base.
RUN python -m venv /opt/cloudcutter-venv \
    && /opt/cloudcutter-venv/bin/pip install --no-cache-dir -r /cloudcutter/src/requirements.txt \
    && /opt/cloudcutter-venv/bin/python -m unittest discover -s /cloudcutter/tests -q
COPY integration/patch_cloudcutter.py /tmp/patch_cloudcutter.py
RUN python /tmp/patch_cloudcutter.py /cloudcutter

FROM ${BUILD_FROM}
ARG BUILD_VERSION=@@VERSION@@
ARG BUILD_ARCH=amd64
RUN apk add --no-cache @@RUNTIME_PACKAGES@@
COPY --from=build /opt/venv /opt/venv
COPY --from=build /opt/cloudcutter-venv /opt/cloudcutter-venv
COPY --from=build /upstream /opt/untuyaos3
COPY --from=build /cloudcutter/custom-firmware/ESPHome-Kickstart-v25.05.28_bk7231t_app.ota.ug.bin /opt/untuyaos3/custom-firmware/BK7231T/
COPY --from=build /cloudcutter/custom-firmware/OpenBeken-v1.18.219_bk7231t.ug.bin /opt/untuyaos3/custom-firmware/BK7231T/
COPY --from=build /cloudcutter/custom-firmware/OpenRTL8710B_UG_1.18.225.img /opt/untuyaos3/custom-firmware/RTL8710BN/OpenRTL8710B_UG_1.18.225.bin
COPY --from=build /cloudcutter/src /opt/cloudcutter/src
COPY --from=build /cloudcutter/device-profiles/schema /opt/cloudcutter/device-profiles/schema
COPY --from=build /cloudcutter/LICENSE /opt/cloudcutter/LICENSE
COPY app/ /opt/webapp/
COPY integration/dhcp.sh /opt/webapp/dhcp.sh
COPY run.sh /run.sh
RUN chmod 755 /opt/webapp/dhcp.sh /run.sh
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UNTUYAOS3_SKIP_INSTALL=1
WORKDIR /opt/webapp
LABEL io.hass.name="Tuya Breaker" io.hass.description="Experimental UnTuyaOS3 and CloudCutter workspace" \
    io.hass.type="addon" io.hass.version="${BUILD_VERSION}" io.hass.arch="${BUILD_ARCH}" \
    org.opencontainers.image.source="https://github.com/seb5594/Home-Assistant-UnTuyaOS3-App"
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["/run.sh"]
