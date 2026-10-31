"""Links and project identity shown in the Web UI: upstream credit, issue reports, the helper app."""
from html import escape
import re
from urllib.parse import urlencode

from protocol import APP_VERSION, BUILD_INFO

MY_HOME_ASSISTANT = "https://my.home-assistant.io/redirect"
def helper_url(hostname=None):
    """A client repository cannot infer the helper's repository hash.

    Before authenticated discovery, open the app store. The helper supplies its
    actual addon_slug afterwards; the Web UI validates it before constructing a link.
    """
    return f"{MY_HOME_ASSISTANT}/supervisor_addons/"


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
