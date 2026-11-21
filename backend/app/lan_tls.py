"""Certificate preflight and continuity of the existing Caddy private CA."""
import hashlib
import ipaddress
import os
import shutil
import ssl
import subprocess
import time


def validate_certificate(path, host):
    executable = shutil.which('openssl')
    if not executable:
        raise ValueError('OpenSSL is required to check supplied certificate identity/dates. Nothing was installed; arrange administrator setup.')
    try:
        ipaddress.ip_address(host)
        flag, label = '-checkip', 'IP'
    except ValueError:
        flag, label = '-checkhost', 'Hostname'
    try:
        result = subprocess.run([executable, 'x509', '-in', str(path), '-noout', '-dates', '-ext', 'subjectAltName', flag, host],
                                check=True, capture_output=True, text=True, timeout=5)
        lines = result.stdout.splitlines()
        if 'X509v3 Subject Alternative Name:' not in result.stdout or f'{label} {host} does match certificate' not in lines:
            raise ValueError(f'TLS certificate must contain a matching SAN for LAN_HOST {host}. Supply the correct certificate; do not change allowlists or bypass browser warnings.')
        dates = dict(line.split('=', 1) for line in lines if line.startswith(('notBefore=', 'notAfter=')))
        if not ssl.cert_time_to_seconds(dates['notBefore']) <= time.time() < ssl.cert_time_to_seconds(dates['notAfter']):
            raise ValueError('TLS certificate is expired or not yet valid. Check the system clock and renew the supplied certificate; do not disable TLS verification.')
    except (OSError, subprocess.SubprocessError, KeyError) as exc:
        raise ValueError('Cannot read supplied TLS certificate identity/dates. Supply a valid PEM leaf/fullchain and matching key; inspect certificate dates and SAN.') from exc


def ca_continuity(state, record=False):
    # The path never contains an IP/hostname. Switching networks must reuse this CA.
    root = state / 'data/caddy/pki/authorities/local'
    certificate, key = root / 'root.crt', root / 'root.key'
    marker = state / 'ca-root.sha256'
    if any(path.is_symlink() for path in (certificate, key, marker)):
        raise ValueError('Caddy CA state must not contain symlinks. Restore the original private LAN_STATE_DIR from a trusted backup.')
    if marker.exists() or certificate.exists() or key.exists():
        if any(not path.is_file() or path.is_symlink() for path in (certificate, key)):
            raise ValueError('Caddy CA state is incomplete. Restore root.crt/root.key from the same trusted backup in LAN_STATE_DIR; automatic CA replacement is refused.')
        try:
            fingerprint = hashlib.sha256(ssl.PEM_cert_to_DER_cert(certificate.read_text())).hexdigest()
        except (ValueError, UnicodeError) as exc:
            raise ValueError('Caddy root CA certificate is invalid. Restore the original CA backup; automatic CA replacement is refused.') from exc
        if marker.exists():
            from .lan_config import private_file
            if private_file(marker).read_text().strip() != fingerprint:
                raise ValueError('Caddy root CA changed unexpectedly. Restore the original LAN_STATE_DIR and CA backup; verify client trust before any intentional CA rotation.')
        elif record:
            descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, 'w') as output:
                output.write(fingerprint + '\n')
                output.flush()
                os.fsync(output.fileno())
    elif record:
        raise ValueError('Caddy did not provision its internal CA. Inspect TLS errors and LAN_STATE_DIR permissions; no robot worker was started.')
