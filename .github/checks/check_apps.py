"""Project checks executed by hass-workflows before building either app."""
import shutil
import subprocess
import sys

subprocess.run([sys.executable, "tools/sync_project.py", "--check"], check=True)
subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], check=True)
subprocess.run(["node", "--check", "untuyaos3/app/static/app.js"], check=True)
subprocess.run(["node", "--check", "tuya_breaker/app/static/breaker.js"], check=True)
subprocess.run(["node", "--check", "tuya_breaker/app/static/hardware.js"], check=True)
subprocess.run(["node", "tests/test_webui.cjs"], check=True)
if not shutil.which("apparmor_parser"):
    subprocess.run(["sudo", "apt-get", "update", "-qq"], check=True)
    subprocess.run(["sudo", "apt-get", "install", "-y", "--no-install-recommends", "apparmor"], check=True)
for app in ("untuyaos3", "untuyaos3_wifi", "tuya_breaker"):
    subprocess.run(["apparmor_parser", "-Q", "-T", f"{app}/apparmor.txt"], check=True)
