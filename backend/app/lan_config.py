"""Private deployment configuration; no live robot state and no hardware imports."""
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
from dataclasses import dataclass
from dotenv import dotenv_values
from .lan_network import RFC1918, detect_lan_ipv4
from .lan_tls import validate_certificate, ca_continuity

ROOT = Path(__file__).resolve().parents[2]
PRIVATE_NETWORKS = (*RFC1918, ipaddress.ip_network('127.0.0.0/8'))
KEYS = {'APP_MODE', 'LAN_HOST', 'LAN_BIND_IP', 'HTTPS_PORT', 'BACKEND_PORT',
        'ALLOWED_HOSTS', 'ALLOWED_ORIGINS', 'OPERATOR_PASSWORD_HASH', 'TLS_MODE',
        'TLS_CERT_FILE', 'TLS_KEY_FILE', 'CADDY_BIN', 'LAN_STATE_DIR',
        'MISSION_DB_PATH', 'ROBOT_CONFIG_PATH', 'ACCOUNT_STORE_PATH'}


def outside_repository(path):
    value = Path(path).expanduser()
    if not value.is_absolute() or value.resolve().is_relative_to(ROOT):
        raise ValueError('Private configuration, TLS and proxy state paths must be absolute and outside the repository')
    return value


def private_file(path):
    value = outside_repository(path)
    info = value.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError(f'{value}: require an owned regular file with chmod 600 (no symlinks)')
    return value


def private_ipv4(value):
    address = ipaddress.IPv4Address(value)
    if not any(address in network for network in PRIVATE_NETWORKS):
        raise ValueError('LAN_BIND_IP must be an RFC1918 private IPv4 address (or loopback for isolated staging)')
    return str(address)


def port(value, name):
    try:
        result = int(value)
        if 1024 <= result <= 65535:
            return result
    except (TypeError, ValueError):
        pass
    raise ValueError(f'{name} must be an integer from 1024 to 65535')


@dataclass(frozen=True)
class LanConfig:
    host: str
    bind: str
    https_port: int
    backend_port: int
    state: Path
    caddy: str
    values: dict

    @property
    def origin(self):
        return f'https://{self.host}:{self.https_port}'

    @classmethod
    def load(cls, filename):
        filename = private_file(filename)
        values = dict(dotenv_values(filename, interpolate=False))
        if set(values) - KEYS:
            raise ValueError('Unknown private config keys: ' + ', '.join(sorted(set(values) - KEYS)))
        if any(v is None or '\n' in v or '\r' in v or '\x00' in v for v in values.values()):
            raise ValueError('Configuration values must be single-line strings')
        if values.get('APP_MODE') != 'lan':
            raise ValueError('Private LAN configuration must explicitly set APP_MODE=lan')
        host = values.get('LAN_HOST', '').lower()
        if len(host) > 253 or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', host):
            raise ValueError('LAN_HOST must be one explicit IPv4 address or DNS hostname, without a scheme, port or wildcard')
        if any(not label or len(label) > 63 or label.startswith('-') or label.endswith('-') for label in host.split('.')):
            raise ValueError('Invalid LAN_HOST DNS label')
        if values.get('LAN_BIND_IP') == 'auto':
            # Automatic address changes must never change the browser/TLS identity.
            try:
                ipaddress.ip_address(host)
            except ValueError:
                if '.' not in host or re.fullmatch(r'[0-9.]+', host):
                    raise ValueError('LAN_BIND_IP=auto requires a stable private DNS hostname, such as amr.home.arpa')
            else:
                raise ValueError('LAN_BIND_IP=auto requires a stable private DNS hostname, not an IP literal')
            bind = detect_lan_ipv4()
        else:
            bind = private_ipv4(values.get('LAN_BIND_IP', ''))
        try:
            addresses = {entry[4][0] for entry in socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)}
        except socket.gaierror as exc:
            raise ValueError(f'LAN_HOST {host} does not resolve to IPv4. Configure its private DNS A record for {bind}; no listener was started.') from exc
        if addresses != {bind}:
            raise ValueError(f'LAN_HOST {host} must resolve only to LAN_BIND_IP {bind}; resolved {", ".join(sorted(addresses)) or "no addresses"}. Update private DNS, clear stale DNS caches and retry; no listener was started.')
        https = port(values.get('HTTPS_PORT', '8443'), 'HTTPS_PORT')
        backend = port(values.get('BACKEND_PORT', '8001'), 'BACKEND_PORT')
        if https == backend:
            raise ValueError('HTTPS_PORT and BACKEND_PORT must differ')
        if values.get('ALLOWED_HOSTS') != host or values.get('ALLOWED_ORIGINS') != f'https://{host}:{https}':
            raise ValueError('ALLOWED_HOSTS must equal LAN_HOST; ALLOWED_ORIGINS must equal https://LAN_HOST:HTTPS_PORT')
        from .accounts import AccountStore
        if not values.get('ACCOUNT_STORE_PATH'):
            raise ValueError('ACCOUNT_STORE_PATH is required. Create accounts or explicitly migrate the legacy hash using app.accounts; existing credentials are not deleted.')
        values['ACCOUNT_STORE_PATH'] = str(private_file(values['ACCOUNT_STORE_PATH']))
        AccountStore(values['ACCOUNT_STORE_PATH']).load()
        mode = values.get('TLS_MODE', 'internal')
        if mode not in ('internal', 'provided'):
            raise ValueError('TLS_MODE must be internal or provided')
        if mode == 'provided':
            for name in ('TLS_CERT_FILE', 'TLS_KEY_FILE'):
                if not values.get(name):
                    raise ValueError(f'{name} is required with TLS_MODE=provided')
                values[name] = str(private_file(values[name]))
            validate_certificate(values['TLS_CERT_FILE'], host)
        elif values.get('TLS_CERT_FILE') or values.get('TLS_KEY_FILE'):
            raise ValueError('TLS certificate/key paths require TLS_MODE=provided')
        state = outside_repository(values.get('LAN_STATE_DIR', str(filename.parent / 'lan-runtime')))
        if state.exists():
            info = state.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError('LAN_STATE_DIR must be an owned directory with chmod 700, without symlinks')
        if mode == 'internal':
            ca_continuity(state)
        for name in ('MISSION_DB_PATH', 'ROBOT_CONFIG_PATH'):
            if name in values and (not Path(values[name]).is_absolute() or values[name] == ':memory:'):
                raise ValueError(f'{name} must be an absolute persistent path')
        executable = values.get('CADDY_BIN', str(ROOT / '.tools' / 'caddy'))
        caddy = shutil.which(executable)
        if not caddy:
            raise ValueError('Caddy not found. Install an approved official user-local binary and set CADDY_BIN; see PHASE5B2_DEPLOYMENT.md. Nothing was installed.')
        return cls(host, bind, https, backend, state, caddy, values)

    def backend_environment(self):
        # Do not inherit stale security or persistence settings from the shell.
        env = {k: v for k, v in os.environ.items() if k not in KEYS and k != 'PYTHONPATH'}
        env.update({k: v for k, v in self.values.items() if k in
                    {'APP_MODE', 'ALLOWED_HOSTS', 'ALLOWED_ORIGINS', 'OPERATOR_PASSWORD_HASH',
                     'MISSION_DB_PATH', 'ROBOT_CONFIG_PATH', 'ACCOUNT_STORE_PATH'}})
        return env

    def caddyfile(self):
        tls = ('internal' if self.values.get('TLS_MODE', 'internal') == 'internal' else
               json.dumps(self.values['TLS_CERT_FILE']) + ' ' + json.dumps(self.values['TLS_KEY_FILE']))
        return '''{
    admin off
    persist_config off
    auto_https disable_redirects
    skip_install_trust
    grace_period 5s
    servers {
        protocols h1 h2
        timeouts {
            read_header 10s
            read_body 15s
            idle 120s
        }
    }
}
https://HOST:HTTPS_PORT {
    bind BIND
    tls TLS_CONFIG
    @outside not remote_ip 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 127.0.0.0/8
    respond @outside "Private LAN clients only" 403
    reverse_proxy 127.0.0.1:BACKEND_PORT {
        # Avoid stale upstream reuse during rapid WebSocket disconnect/reconnect.
        # Browser HTTPS keepalive and established WebSockets remain enabled.
        transport http {
            keepalive off
            dial_timeout 3s
            response_header_timeout 5s
        }
        header_up Host {http.request.hostport}
        header_up X-Forwarded-For {http.request.remote.host}
        header_up X-Forwarded-Proto https
        header_up -Forwarded
    }
}
https://:HTTPS_PORT {
    bind BIND
    respond "Host is not allowed" 421
}
'''.replace('HOST', self.host).replace('HTTPS_PORT', str(self.https_port)).replace('BIND', self.bind).replace('TLS_CONFIG', tls).replace('BACKEND_PORT', str(self.backend_port))
