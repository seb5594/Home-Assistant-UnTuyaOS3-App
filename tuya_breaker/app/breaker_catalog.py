"""Bounded, explicit downloads from the official profile API; no executable hooks."""
import json
from pathlib import Path
import re
from urllib.request import urlopen

API = 'https://tuya-cloudcutter.github.io/api/'
SLUG = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,199}')
CHIPS = {'BK7231T', 'BK7231N', 'RTL8710BN', 'RTL8720CF'}


def slug(value):
    if not isinstance(value, str) or not SLUG.fullmatch(value) or '..' in value:
        raise ValueError('Invalid device/profile identifier')
    return value


def download(path, limit=2*1024*1024):
    with urlopen(API + path, timeout=15) as response:
        # Do not follow a profile API redirect onto an unrelated service.
        if not response.url.startswith(API):
            raise ValueError('Unexpected profile API destination')
        raw = response.read(limit+1)
    if len(raw) > limit:
        raise ValueError('Profile API response exceeds the size limit')
    return json.loads(raw)


def validate_profile(device, profile):
    if not isinstance(device, dict) or not isinstance(profile, dict):
        raise ValueError('Invalid profile response')
    if profile.get('type') != 'CLASSIC' or profile.get('firmware', {}).get('chip', '').upper() not in CHIPS:
        raise ValueError('Only classic CloudCutter profiles for supported chips are accepted')
    if not isinstance(device.get('schemas'), dict) or not device['schemas']:
        raise ValueError('Device profile lacks the endpoint schema')
    if not isinstance(profile.get('data'), dict) or not profile['data']:
        raise ValueError('Profile lacks exploit data')
    if profile.get('slug') not in [p.get('slug') for p in device.get('profiles', [])]:
        raise ValueError('The selected profile does not belong to this device')


class Catalogue:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def devices(self, refresh=False):
        path = self.root / 'catalogue.json'
        if refresh:
            data = download('devices.json', 8*1024*1024)
            if not isinstance(data, list) or len(data) > 20000:
                raise ValueError('Invalid device catalogue')
            data = [{'slug': slug(d['slug']), 'manufacturer': str(d['manufacturer'])[:200],
                     'name': str(d['name'])[:300]} for d in data]
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps(data), encoding='utf-8')
            temp.replace(path)
        return json.loads(path.read_text()) if path.exists() else []

    def device(self, value):
        return download('devices/' + slug(value) + '.json')

    def profiles(self, value):
        device = self.device(value)
        result = []
        for entry in device.get('profiles', [])[:8]:
            if entry.get('type') == 'CLASSIC':
                profile = download('profiles/' + slug(entry['slug']) + '.json')
                validate_profile(device, profile)
                result.append({'slug': entry['slug'], 'name': profile['name'],
                               'firmware': profile['firmware']})
        return result

    def combined(self, device_slug, profile_slug):
        device_slug, profile_slug = slug(device_slug), slug(profile_slug)
        device = self.device(device_slug)
        profile = download('profiles/' + profile_slug + '.json')
        validate_profile(device, profile)
        combined = {'slug': device_slug, 'device': device, 'profile': profile}
        path = self.root / 'selected-profile.json'
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(combined), encoding='utf-8')
        temp.replace(path)
        return path, combined
