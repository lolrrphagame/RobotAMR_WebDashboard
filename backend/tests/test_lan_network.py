"""Isolated network snapshots: never change host routes, DNS, interfaces or trust."""
import copy
import json
import socket
import subprocess
import pytest
from app import lan_network
from app.lan_config import LanConfig
from app.lan_tls import ca_continuity, validate_certificate
from test_lan_deployment import config_file


@pytest.fixture
def network(monkeypatch):
    monkeypatch.setattr(lan_network, 'physical_interface', lambda name: True)
    return {
        'addresses': [{'ifname': 'wlan0', 'flags': ['UP'], 'operstate': 'UP', 'addr_info': [
            {'family': 'inet', 'scope': 'global', 'local': '192.168.10.20', 'prefixlen': 24}]}],
        'links': [{'ifname': 'wlan0', 'flags': ['UP'], 'operstate': 'UP', 'link_type': 'ether'}],
        'routes': [{'dst': 'default', 'dev': 'wlan0', 'gateway': '192.168.10.1'},
                   {'dst': '192.168.10.0/24', 'dev': 'wlan0', 'scope': 'link'}],
        'rules': [{'priority': 0, 'src': 'all', 'table': 'local'},
                  {'priority': 32766, 'src': 'all', 'table': 'main'},
                  {'priority': 32767, 'src': 'all', 'table': 'default'}],
    }


def test_select_single_physical_private_address_and_ignore_loopback(network):
    network['addresses'].append({'ifname': 'lo', 'flags': ['UP'], 'addr_info': [{'family': 'inet', 'scope': 'host', 'local': '127.0.0.1'}]})
    network['routes'].append({'type': 'local', 'dev': 'lo', 'table': 'local', 'dst': '127.0.0.1'})
    assert lan_network.select_lan_ipv4(**network) == '192.168.10.20'


@pytest.mark.parametrize('address', ['8.8.8.8', '127.0.0.1', '169.254.1.1', '224.0.0.1', '0.0.0.0', '192.0.2.10', '192.168.10.0', '192.168.10.255'])
def test_reject_public_reserved_loopback_and_unusable_addresses(network, address):
    network['addresses'][0]['addr_info'][0]['local'] = address
    with pytest.raises(ValueError, match='RFC1918'):
        lan_network.select_lan_ipv4(**network)


@pytest.mark.parametrize('kind', ['second_interface', 'second_address', 'no_address', 'two_defaults', 'no_default', 'multipath',
                                      'policy_rule', 'policy_table', 'vpn_route', 'split_default', 'virtual', 'down',
                                      'no_physical_device', 'public_gateway', 'off_subnet_gateway', 'wrong_source', 'deprecated'])
def test_unsafe_or_ambiguous_networks_fail_closed(network, monkeypatch, kind):
    if kind == 'second_interface':
        extra = copy.deepcopy(network['addresses'][0]); extra['ifname'] = 'eth0'; network['addresses'].append(extra)
    elif kind == 'second_address':network['addresses'][0]['addr_info'].append(copy.deepcopy(network['addresses'][0]['addr_info'][0]))
    elif kind == 'no_address':network['addresses'] = []
    elif kind == 'two_defaults':network['routes'].append(copy.deepcopy(network['routes'][0]))
    elif kind == 'no_default':network['routes'].pop(0)
    elif kind == 'multipath':network['routes'][0]['multipath'] = [{'dev': 'wlan0'}]
    elif kind == 'policy_rule':network['rules'].append({'priority': 100, 'src': 'all', 'table': 100})
    elif kind == 'policy_table':network['routes'].append({'dst': 'default', 'dev': 'wlan0', 'table': 100})
    elif kind == 'vpn_route':network['routes'].append({'dst': '10.8.0.0/24', 'dev': 'tun0'})
    elif kind == 'split_default':network['routes'].append({'dst': '128.0.0.0/1', 'dev': 'wlan0'})
    elif kind == 'virtual':network['links'][0]['linkinfo'] = {'info_kind': 'wireguard'}
    elif kind == 'down':network['links'][0]['operstate'] = 'DOWN'
    elif kind == 'no_physical_device':monkeypatch.setattr(lan_network, 'physical_interface', lambda name: False)
    elif kind == 'public_gateway':network['routes'][0]['gateway'] = '8.8.8.8'
    elif kind == 'off_subnet_gateway':network['routes'][0]['gateway'] = '192.168.20.1'
    elif kind == 'wrong_source':network['routes'][0]['prefsrc'] = '192.168.10.21'
    else:network['addresses'][0]['addr_info'][0]['preferred_life_time'] = 0
    with pytest.raises(ValueError, match='Automatic LAN detection'):
        lan_network.select_lan_ipv4(**network)


def test_detection_uses_only_bounded_read_only_queries(network, monkeypatch):
    calls = []
    def query(*args):
        calls.append(args)
        return network['addresses' if 'address' in args else 'links' if 'link' in args else 'rules' if 'rule' in args else 'routes']
    monkeypatch.setattr(lan_network, 'ip_json', query)
    assert lan_network.detect_lan_ipv4() == '192.168.10.20'
    assert len(calls) == 4
    assert all('show' in call and not {'add', 'set', 'delete', 'get'} & set(call) for call in calls)


@pytest.mark.parametrize('failure', ['missing', 'timeout', 'malformed', 'wrong_shape'])
def test_network_inspection_failures_are_actionable(monkeypatch, failure):
    monkeypatch.setattr(lan_network.shutil, 'which', lambda name: None if failure == 'missing' else '/sbin/ip')
    def run(*args, **kwargs):
        assert kwargs['timeout'] == 5 and kwargs['capture_output'] is True
        if failure == 'timeout':raise subprocess.TimeoutExpired(args[0], 5)
        return subprocess.CompletedProcess(args[0], 0, stdout='{' if failure == 'malformed' else '{}')
    monkeypatch.setattr(lan_network.subprocess, 'run', run)
    with pytest.raises(ValueError, match='Nothing was installed|Cannot inspect'):
        lan_network.ip_json('-4', 'address', 'show')


def auto_config(tmp_path):
    return config_file(tmp_path, LAN_BIND_IP='auto', LAN_HOST='amr.home.arpa', ALLOWED_HOSTS='amr.home.arpa',
                       ALLOWED_ORIGINS='https://amr.home.arpa:18443', CADDY_BIN='/bin/true')


def dns(monkeypatch, addresses):
    monkeypatch.setattr('app.lan_config.socket.getaddrinfo', lambda *args: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (address, 0)) for address in addresses])


def test_dhcp_changes_update_only_bind_and_preserve_hostname_ca_and_private_file(tmp_path, monkeypatch, certificate):
    path = auto_config(tmp_path)
    original = path.read_bytes()
    monkeypatch.setattr('app.lan_config.detect_lan_ipv4', lambda: '192.168.10.20')
    dns(monkeypatch, ['192.168.10.20'])
    first = LanConfig.load(path)
    first.state.mkdir(mode=0o700)
    root = first.state / 'data/caddy/pki/authorities/local'; root.mkdir(parents=True)
    original_ca=certificate.read_bytes()
    (root / 'root.crt').write_bytes(original_ca); (root / 'root.key').write_bytes(b'isolated-test-key')
    ca_continuity(first.state, record=True)
    fingerprint = (first.state / 'ca-root.sha256').read_bytes()
    monkeypatch.setattr('app.lan_config.detect_lan_ipv4', lambda: '10.20.30.40')
    dns(monkeypatch, ['10.20.30.40'])
    second = LanConfig.load(path)
    assert first.bind == '192.168.10.20' and second.bind == '10.20.30.40'
    assert first.origin == second.origin == 'https://amr.home.arpa:18443'
    assert first.state == second.state
    assert 'bind 10.20.30.40' in second.caddyfile() and 'bind 192.168.10.20' not in second.caddyfile()
    env = second.backend_environment()
    assert env['APP_MODE'] == 'lan' and env['ALLOWED_HOSTS'] == 'amr.home.arpa' and env['ACCOUNT_STORE_PATH']
    assert env['ALLOWED_ORIGINS'] == second.origin
    assert 'reverse_proxy 127.0.0.1:18001' in second.caddyfile() and '*' not in env['ALLOWED_HOSTS'] + env['ALLOWED_ORIGINS']
    assert (first.state / 'ca-root.sha256').read_bytes() == fingerprint and (root / 'root.crt').read_bytes() == original_ca
    assert path.read_bytes() == original and not (tmp_path / 'missions.sqlite3').exists()


@pytest.mark.parametrize('addresses', [[], ['192.168.10.21'], ['192.168.10.20', '192.168.10.21'], ['8.8.8.8'], ['127.0.0.1']])
def test_stale_ambiguous_or_unsafe_dns_rejects_before_data_or_proxy(tmp_path, monkeypatch, addresses):
    path = auto_config(tmp_path)
    monkeypatch.setattr('app.lan_config.detect_lan_ipv4', lambda: '192.168.10.20')
    dns(monkeypatch, addresses)
    with pytest.raises(ValueError, match='Update private DNS'):
        LanConfig.load(path)
    assert not (tmp_path / 'missions.sqlite3').exists() and not (tmp_path / 'runtime').exists()


def test_unresolved_dns_is_actionable(tmp_path, monkeypatch):
    path = auto_config(tmp_path)
    monkeypatch.setattr('app.lan_config.detect_lan_ipv4', lambda: '192.168.10.20')
    def fail(*args):raise socket.gaierror('not found')
    monkeypatch.setattr('app.lan_config.socket.getaddrinfo', fail)
    with pytest.raises(ValueError, match='private DNS A record for 192.168.10.20'):
        LanConfig.load(path)


def test_explicit_loopback_staging_does_not_use_auto_detection(tmp_path, monkeypatch):
    def fail():raise AssertionError('Explicit mode must not auto-detect')
    monkeypatch.setattr('app.lan_config.detect_lan_ipv4', fail)
    assert LanConfig.load(config_file(tmp_path, CADDY_BIN='/bin/true')).bind == '127.0.0.1'
    with pytest.raises(ValueError, match='stable private DNS hostname'):
        LanConfig.load(config_file(tmp_path, LAN_BIND_IP='auto'))


@pytest.mark.parametrize('damage', ['certificate', 'key', 'both', 'replacement'])
def test_ca_loss_or_replacement_fails_instead_of_regenerating(tmp_path, damage, certificate):
    root=tmp_path/'data/caddy/pki/authorities/local';root.mkdir(parents=True)
    (root/'root.crt').write_bytes(certificate.read_bytes());(root/'root.key').write_bytes(b'original-key')
    ca_continuity(tmp_path, record=True)
    if damage in ('certificate', 'both'):(root/'root.crt').unlink()
    if damage in ('key', 'both'):(root/'root.key').unlink()
    if damage == 'replacement':(root/'root.crt').write_bytes(b'replacement-ca')
    with pytest.raises(ValueError, match='CA state is incomplete|root CA changed|CA certificate is invalid'):
        ca_continuity(tmp_path)


@pytest.fixture
def certificate(tmp_path):
    cert=tmp_path/'server.pem';key=tmp_path/'server.key'
    subprocess.run(['openssl','req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256','-nodes',
                    '-keyout',str(key),'-out',str(cert),'-days','2','-subj','/CN=amr.home.arpa',
                    '-addext','subjectAltName=DNS:amr.home.arpa'], check=True, capture_output=True)
    return cert


def test_provided_certificate_is_checked_against_stable_hostname(certificate):
    validate_certificate(certificate,'amr.home.arpa')
    with pytest.raises(ValueError,match='matching SAN|Cannot read'):
        validate_certificate(certificate,'other.home.arpa')


@pytest.mark.parametrize('now', [0, 100000000000])
def test_expired_or_not_yet_valid_certificate_is_actionable(certificate, monkeypatch, now):
    monkeypatch.setattr('app.lan_tls.time.time', lambda: now)
    with pytest.raises(ValueError,match='expired or not yet valid'):
        validate_certificate(certificate,'amr.home.arpa')
