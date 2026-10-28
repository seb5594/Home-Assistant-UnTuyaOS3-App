"""Links and project identity shown in the Web UI: upstream credit, issue reports, the helper app."""
from html import escape
import re
import socket
from urllib.parse import urlencode

from protocol import APP_VERSION, BUILD_INFO

MY_HOME_ASSISTANT = "https://my.home-assistant.io/redirect"
HELPER_SLUG = "untuyaos3_wifi"
# Home Assistant names the container "<repository hash>-<app slug>" with dashes. The same
# hash prefixes the helper's slug, because both apps come from one repository.
OWN_HOSTNAME = re.compile(r"(?P<repository>[0-9a-f]{8}|local)-(?:untuyaos3|tuya-breaker)")


def helper_url(hostname=None):
    """Deep link to the helper's page in Home Assistant, or to the app store if we cannot tell."""
    match = OWN_HOSTNAME.fullmatch(hostname or socket.gethostname())
    if not match:
        return f"{MY_HOME_ASSISTANT}/supervisor_addons/"
    return f"{MY_HOME_ASSISTANT}/supervisor_addon/?" + urlencode({"addon": f"{match['repository']}_{HELPER_SLUG}"})


def upstream_url():
    return "https://github.com/" + BUILD_INFO["upstream_repository"]


def report_url():
    """Issue form for compatibility reports; the Web UI appends details about the adapter."""
    base = BUILD_INFO["repository_url"] + "/issues/new?"
    return base + urlencode({"template": "device-report.yml", "app_version": APP_VERSION,
                             "upstream_revision": BUILD_INFO["upstream_revision"][:7]})


def page_values(csrf, hostname=None):
    """Placeholders (``__NAME__``) that the index page template expects."""
    revision = BUILD_INFO["upstream_revision"]
    values = {"CSRF": csrf, "VERSION": APP_VERSION, "REPOSITORY_URL": BUILD_INFO["repository_url"],
              "UPSTREAM_URL": upstream_url(), "UPSTREAM_REVISION": revision[:7],
              "UPSTREAM_COMMIT_URL": f"{upstream_url()}/commit/{revision}",
              "HELPER_URL": helper_url(hostname), "REPORT_URL": report_url()}
    return {name: escape(value, quote=True) for name, value in values.items()}


def render_page(template, csrf, hostname=None):
    """Fill the index template. Every value is HTML-escaped; none comes from a request."""
    values = page_values(csrf, hostname)
    return re.sub(r"__([A-Z_]+)__", lambda match: values.get(match[1], match[0]), template)
