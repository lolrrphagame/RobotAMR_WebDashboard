"""Temporary test CA + Chromium NSS trust. Never changes the user's/system trust."""
import ctypes
import ctypes.util
import os
from pathlib import Path
import subprocess
import ssl
import sys

directory = Path(sys.argv[1]).resolve()
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'backend'))
from app.security import password_hash
from app.accounts import AccountStore


def openssl(*args):
    subprocess.run(['openssl', *args], cwd=directory, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


os.umask(0o077)
openssl('req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', 'ca.key', '-out', 'ca.crt',
        '-days', '2', '-subj', '/CN=PBL4 isolated browser test CA', '-addext', 'basicConstraints=critical,CA:TRUE',
        '-addext', 'keyUsage=critical,keyCertSign,cRLSign')
openssl('req', '-newkey', 'rsa:2048', '-nodes', '-keyout', 'server.key', '-out', 'server.csr', '-subj', '/CN=127.0.0.1')
(directory / 'server.ext').write_text('subjectAltName=IP:127.0.0.1\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n')
openssl('x509', '-req', '-in', 'server.csr', '-CA', 'ca.crt', '-CAkey', 'ca.key', '-CAcreateserial',
        '-out', 'server.crt', '-days', '2', '-extfile', 'server.ext')

# Chromium >= M146 supports XDG_DATA_HOME/pki/nssdb. A private DB, not HOME, is used.
# NSS declarations: https://github.com/nss-dev/nss/tree/master/lib/certdb
db = directory / 'browser-data/pki/nssdb'
db.mkdir(parents=True, mode=0o700)
library = ctypes.util.find_library('nss3')
if not library:
    raise SystemExit('LAN browser tests require the existing Chromium NSS library; no packages are installed automatically')
nss = ctypes.CDLL(library)


class Trust(ctypes.Structure):
    _fields_ = [('sslFlags', ctypes.c_uint), ('emailFlags', ctypes.c_uint), ('objectSigningFlags', ctypes.c_uint)]


class Item(ctypes.Structure):
    _fields_ = [('type', ctypes.c_uint), ('data', ctypes.c_void_p), ('length', ctypes.c_uint)]


def declare(name, arguments, result=ctypes.c_int):
    function = getattr(nss, name)
    function.argtypes, function.restype = arguments, result
    return function


initialize = declare('NSS_InitReadWrite', [ctypes.c_char_p])
get_db = declare('CERT_GetDefaultCertDB', [], ctypes.c_void_p)
decode = declare('CERT_NewTempCertificate', [ctypes.c_void_p, ctypes.POINTER(Item), ctypes.c_char_p, ctypes.c_int, ctypes.c_int], ctypes.c_void_p)
decode_trust = declare('CERT_DecodeTrustString', [ctypes.POINTER(Trust), ctypes.c_char_p])
get_slot = declare('PK11_GetInternalKeySlot', [], ctypes.c_void_p)
needs_pin = declare('PK11_NeedUserInit', [ctypes.c_void_p])
init_pin = declare('PK11_InitPin', [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p])
persist = declare('PK11_ImportCert', [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_char_p, ctypes.c_int])
change_trust = declare('CERT_ChangeCertTrust', [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(Trust)])
free_slot = declare('PK11_FreeSlot', [ctypes.c_void_p], None)
destroy = declare('CERT_DestroyCertificate', [ctypes.c_void_p], None)
shutdown = declare('NSS_Shutdown', [])
assert initialize(('sql:' + str(db)).encode()) == 0, 'Cannot initialize isolated browser NSS trust database'
certificate = None
slot = None
try:
    der = ssl.PEM_cert_to_DER_cert((directory / 'ca.crt').read_text())
    buffer = ctypes.create_string_buffer(der)
    item = Item(0, ctypes.cast(buffer, ctypes.c_void_p), len(der))
    handle = get_db()
    certificate = decode(handle, ctypes.byref(item), None, 0, 1)
    assert certificate, 'Cannot decode temporary test CA'
    trust = Trust()
    assert decode_trust(ctypes.byref(trust), b'C,,') == 0
    slot = get_slot()
    assert slot
    if needs_pin(slot):
        assert init_pin(slot, None, b'') == 0
    assert persist(slot, certificate, 0, b'PBL4 temporary test CA', 0) == 0
    assert change_trust(handle, certificate, ctypes.byref(trust)) == 0, 'Cannot trust test CA in isolated browser database'
finally:
    if certificate:
        destroy(certificate)
    if slot:
        free_slot(slot)
    assert shutdown() == 0

accounts = AccountStore(directory / 'accounts.json')
accounts.create('operator', 'operator', password_hash('isolated-browser-password'))
accounts.create('observer', 'observer', password_hash('isolated-observer-password'))
config = {
    'APP_MODE': 'lan', 'LAN_HOST': '127.0.0.1', 'LAN_BIND_IP': '127.0.0.1',
    'HTTPS_PORT': '18443', 'BACKEND_PORT': '18001', 'ALLOWED_HOSTS': '127.0.0.1',
    'ALLOWED_ORIGINS': 'https://127.0.0.1:18443', 'OPERATOR_PASSWORD_HASH': password_hash('isolated-browser-password'),
    'ACCOUNT_STORE_PATH': str(directory / 'accounts.json'),
    'TLS_MODE': 'provided', 'TLS_CERT_FILE': str(directory / 'server.crt'), 'TLS_KEY_FILE': str(directory / 'server.key'),
    'CADDY_BIN': str(root / '.tools/caddy'), 'LAN_STATE_DIR': str(directory / 'runtime'),
    'MISSION_DB_PATH': str(directory / 'missions.sqlite3'), 'ROBOT_CONFIG_PATH': str(directory / 'robot-config.json'),
}
(directory / 'lan.env').write_text('\n'.join(k + '=' + v for k, v in config.items()) + '\n')
