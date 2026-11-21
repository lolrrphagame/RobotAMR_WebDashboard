"""Conservative startup-only Linux LAN discovery. Read-only; no outbound probes."""
import ipaddress
import json
from pathlib import Path
import shutil
import subprocess

RFC1918 = tuple(ipaddress.ip_network(value) for value in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
GUIDANCE = 'Inspect ip -4 address, ip -4 route show table all and ip -4 rule. Disconnect VPNs/unused interfaces or use an explicitly reviewed LAN_BIND_IP.'


def ip_json(*arguments):
    executable = shutil.which('ip')
    if not executable:
        raise ValueError('Automatic LAN detection needs the existing Linux ip command. Nothing was installed; use an explicit LAN_BIND_IP or arrange administrator setup.')
    try:
        result = subprocess.run([executable, '-j', *arguments], check=True, capture_output=True, text=True, timeout=5)
        value = json.loads(result.stdout)
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise ValueError()
        return value
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise ValueError('Cannot inspect Linux networking safely for automatic LAN detection. ' + GUIDANCE) from exc


def physical_interface(name):
    return bool(name and '/' not in name and (Path('/sys/class/net') / name / 'device').exists())


def select_lan_ipv4(addresses, links, routes, rules):
    """Fail closed for dual-homing, tunnels, policy routing and multi-address NICs."""
    def reject(reason):
        raise ValueError('Automatic LAN detection: ' + reason + '. ' + GUIDANCE)

    # Only Linux's ordinary local/main/default policy rules are supported.
    expected = {(0, 'local'), (32766, 'main'), (32767, 'default')}
    tables = {255: 'local', 254: 'main', 253: 'default'}
    observed = set()
    for rule in rules:
        table = tables.get(rule.get('table'), rule.get('table'))
        if set(rule) - {'priority', 'src', 'table', 'protocol'} or rule.get('src') != 'all':
            reject('VPN or custom policy-routing rules are unsupported')
        observed.add((rule.get('priority'), table))
    if observed != expected or len(rules) != 3:
        reject('VPN or custom policy-routing rules are unsupported')

    by_name = {link.get('ifname'): link for link in links}
    candidates = []
    for interface in addresses:
        if interface.get('ifname') == 'lo' or 'UP' not in interface.get('flags', []) or interface.get('operstate') == 'DOWN':
            continue
        for address in interface.get('addr_info', []):
            if address.get('family') == 'inet' and address.get('scope') == 'global':
                candidates.append((interface['ifname'], address))
    if len(candidates) != 1:
        reject('expected exactly one active interface with one global IPv4 address; found ' + str(len(candidates)))
    name, address = candidates[0]
    link = by_name.get(name, {})
    if (link.get('link_type') != 'ether' or link.get('linkinfo') or 'POINTOPOINT' in link.get('flags', [])
            or 'UP' not in link.get('flags', []) or link.get('operstate') != 'UP' or not physical_interface(name)):
        reject('the selected interface is not an active physical Ethernet/Wi-Fi interface (VPN/virtual interfaces are unsupported)')
    try:
        interface = ipaddress.IPv4Interface(f'{address["local"]}/{address["prefixlen"]}')
    except (KeyError, ValueError) as exc:
        raise ValueError('Automatic LAN detection: invalid interface address. ' + GUIDANCE) from exc
    if (not any(interface.network.subnet_of(network) for network in RFC1918)
            or interface.network.prefixlen > 30 or interface.ip in (interface.network.network_address, interface.network.broadcast_address)
            or address.get('deprecated') or address.get('tentative') or address.get('dadfailed')
            or address.get('preferred_life_time') == 0 or address.get('valid_life_time') == 0):
        reject('selected address must be a usable, non-deprecated RFC1918 LAN address and subnet')

    defaults = []
    for route in routes:
        if route.get('type', 'unicast') in ('local', 'broadcast') and route.get('table') in ('local', 255):
            continue
        if (route.get('type', 'unicast') != 'unicast' or route.get('table', 'main') not in ('main', 254)
                or route.get('dev') != name or route.get('multipath') or route.get('nexthops') or route.get('nhid') or route.get('encap')
                or route.get('flags')):
            reject('VPN, alternate-interface/table, multipath or invalid IPv4 routes are present')
        if route.get('dst') in ('default', '0.0.0.0/0'):
            defaults.append(route)
        else:
            try:
                destination = ipaddress.IPv4Network(route.get('dst', ''), strict=False)
            except ValueError:
                reject('invalid IPv4 route destination')
            if destination.prefixlen <= 1:
                reject('split-default VPN routes are unsupported')
    if len(defaults) != 1:
        reject('expected exactly one IPv4 default route; found ' + str(len(defaults)))
    try:
        gateway = ipaddress.IPv4Address(defaults[0].get('gateway', ''))
    except ValueError:
        reject('the default route needs a directly connected private gateway')
    if gateway not in interface.network or gateway in (interface.ip, interface.network.network_address, interface.network.broadcast_address):
        reject('the default gateway must be a different usable address in the selected private subnet')
    source = defaults[0].get('prefsrc')
    if source and source != str(interface.ip):
        reject('default route source does not match the selected interface address')
    return str(interface.ip)


def detect_lan_ipv4():
    try:
        return select_lan_ipv4(ip_json('-4', 'address', 'show'), ip_json('-d', 'link', 'show'),
                               ip_json('-4', 'route', 'show', 'table', 'all'), ip_json('-4', 'rule', 'show'))
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError('Automatic LAN detection: unsupported network data. ' + GUIDANCE) from exc
