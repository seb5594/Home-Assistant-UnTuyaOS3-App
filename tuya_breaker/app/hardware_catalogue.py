"""Read-only OpenBeken/Elektroda hardware context, never exploit compatibility."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen

SOURCE = 'https://openbekeniot.github.io/webapp/devices.json'
SOURCE_PAGE = 'https://openbekeniot.github.io/webapp/devicesList.html'
MAX_DOWNLOAD = 12 * 1024 * 1024
GUIDE_HOSTS = {'www.elektroda.com', 'elektroda.com', 'www.elektroda.pl', 'elektroda.pl',
               'github.com', 'openbekeniot.github.io'}


def text(value, limit=300):
    return ''.join(c if ord(c) >= 32 else ' ' for c in value)[:limit].strip() if isinstance(value, str) else ''


def guide_url(value):
    if not isinstance(value, str) or any(ord(c)<32 for c in value):
        return ''
    try:
        url = urlsplit(value)
        if url.scheme not in ('https','http') or url.hostname not in GUIDE_HOSTS or url.username or url.password or url.port:
            return ''
        return urlunsplit(('https',url.netloc,url.path,url.query,url.fragment))
    except ValueError:
        return ''


def normalize(device):
    if not isinstance(device, dict) or not text(device.get('name')):
        return None
    keywords = device.get('keywords', [])
    keywords = [text(item,80) for item in keywords[:40] if isinstance(item,str)] if isinstance(keywords,list) else []
    pins = device.get('pins', {})
    pins = {text(str(key),16):text(value,128) for key,value in list(pins.items())[:64]} if isinstance(pins,dict) else {}
    template = {key:text(device.get(key),4000 if key=='command' else 300)
                for key in ('name','vendor','model','chip','board','flags','command') if key in device}
    template.update(pins=pins, keywords=keywords)
    identity = hashlib.sha256(json.dumps(device,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]
    return {'id':identity, 'name':text(device.get('name')), 'vendor':text(device.get('vendor'),100),
            'model':text(device.get('model'),180), 'chip':text(device.get('chip'),80),
            'board':text(device.get('board'),100), 'keywords':keywords,
            'detailed':device.get('bDetailed') in ('1',1,True), 'has_template':bool(pins),
            'guide_url':guide_url(device.get('wiki')), 'template':template,
            'cloudcutter_verified':False}


class HardwareCatalogue:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root/'hardware.json'

    def snapshot(self, refresh=False):
        if refresh:
            with urlopen(SOURCE, timeout=20) as response:
                if response.url != SOURCE:
                    raise ValueError('Unexpected hardware database destination')
                raw = response.read(MAX_DOWNLOAD+1)
            if len(raw)>MAX_DOWNLOAD:
                raise ValueError('Hardware database exceeds the download limit')
            data = json.loads(raw)
            if not isinstance(data,dict) or not isinstance(data.get('devices'),list) or len(data['devices'])>20000:
                raise ValueError('Unexpected OpenBeken hardware database format')
            devices = [record for device in data['devices'] if (record:=normalize(device)) is not None]
            result = {'source':SOURCE, 'source_page':SOURCE_PAGE,
                      'credits':'OpenBeken / openshwprojects and the Elektroda.com community',
                      'updated_at':datetime.now(timezone.utc).isoformat(), 'version':str(data.get('version','unknown'))[:40],
                      'source_sha256':hashlib.sha256(raw).hexdigest(), 'devices':devices}
            encoded = json.dumps(result,ensure_ascii=False)
            if len(encoded.encode())>24*1024*1024:
                raise ValueError('Normalized hardware database exceeds the cache limit')
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(encoded,encoding='utf-8')
            temporary.replace(self.path)
        if not self.path.exists():
            return {'source':SOURCE,'source_page':SOURCE_PAGE,'updated_at':None,'devices':[]}
        data = json.loads(self.path.read_text(encoding='utf-8'))
        return {**data, 'devices':[{key:value for key,value in device.items() if key!='template'} for device in data['devices']]}

    def detail(self, identity):
        if not re.fullmatch(r'[0-9a-f]{20}',identity):
            raise ValueError('Invalid hardware record')
        data = json.loads(self.path.read_text(encoding='utf-8'))
        for device in data['devices']:
            if device['id']==identity:
                return {**device,'source':SOURCE,'source_page':SOURCE_PAGE,'updated_at':data['updated_at']}
        raise ValueError('Hardware record no longer available; refresh the list')
