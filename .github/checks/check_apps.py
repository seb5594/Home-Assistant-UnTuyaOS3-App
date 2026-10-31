"""Validate this standalone app, generated files and regression suite."""
import pathlib, shutil, subprocess, sys
subprocess.run([sys.executable,'tools/sync_project.py','--check'],check=True)
subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],check=True)
root=pathlib.Path('.')
apps=list(root.glob('*/config.yaml'))
for path in apps:
    for script in (path.parent/'app/static').glob('*.js'):
        subprocess.run(['node','--check',str(script)],check=True)
if (root/'tests/test_webui.cjs').exists():
    subprocess.run(['node','tests/test_webui.cjs'],check=True)
if not shutil.which('apparmor_parser'):
    subprocess.run(['sudo','apt-get','update','-qq'],check=True)
    subprocess.run(['sudo','apt-get','install','-y','--no-install-recommends','apparmor'],check=True)
for path in apps:
    subprocess.run(['apparmor_parser','-Q','-T',str(path.parent/'apparmor.txt')],check=True)
