"""Private, atomic account storage and host-administrator CLI. No HTTP admin API."""
import argparse
from contextlib import contextmanager
import fcntl
import getpass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
from .lan_config import outside_repository, private_file


def username(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}', value):
        raise ValueError('Username must contain 1–64 letters, digits, dots, underscores or hyphens')
    return value.casefold()


def hash_parts(encoded):
    if not isinstance(encoded, str):
        raise ValueError('Password hash must be an encoded scrypt string')
    if encoded.startswith('scrypt$'):
        method, n, r, p, salt, digest = encoded.split('$')
        if (n, r, p) != ('32768', '8', '3'):
            raise ValueError('Unsupported scrypt parameters')
        n, r, p = int(n), int(r), int(p)
    else:
        salt, digest = encoded.split(':')  # Existing Phase 5A credential; never silently removed.
        n, r, p = 16384, 8, 1
    if not 16 <= len(bytes.fromhex(salt)) <= 64 or len(bytes.fromhex(digest)) != 64 or len(digest) != 128:
        raise ValueError('Invalid scrypt hash')
    return n, r, p, salt, digest


def make_password_hash(password):
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise ValueError('Use a password containing 12–256 characters')
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=3,
                            maxmem=64 * 1024 * 1024).hex()
    return f'scrypt$32768$8$3${salt}${digest}'


def verify_password(password, encoded):
    n, r, p, salt, expected = hash_parts(encoded)
    actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=n, r=r, p=p,
                            maxmem=64 * 1024 * 1024).hex()
    return hmac.compare_digest(actual, expected)


class AccountStore:
    def __init__(self, path):
        self.path = outside_repository(path)
        self.signature = None
        self.users = None

    def load(self):
        path = private_file(self.path)
        info = path.stat()
        signature = (info.st_ino, info.st_mtime_ns, info.st_ctime_ns, info.st_size)
        if signature == self.signature:
            return self.users
        if info.st_size > 512 * 1024:
            raise ValueError('Account store exceeds size limit')
        body = json.loads(path.read_text())
        if not isinstance(body, dict):
            raise ValueError('Invalid account store document')
        users = body.get('users')
        if body.get('version') != 1 or not isinstance(users, dict) or len(users) > 128:
            raise ValueError('Invalid account store version or capacity')
        for name, user in users.items():
            if username(name) != name or not isinstance(user, dict) or user.get('role') not in ('operator', 'observer'):
                raise ValueError('Invalid account record')
            if type(user.get('enabled')) is not bool or not isinstance(user.get('revision'), str) or len(user['revision']) != 32:
                raise ValueError('Invalid account state')
            hash_parts(user.get('password_hash'))
        self.signature, self.users = signature, users
        return users

    @contextmanager
    def edit(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(self.path.suffix + '.lock')
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'a') as lock:
            os.fchmod(lock.fileno(), 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.signature = None
            users = dict(self.load()) if self.path.exists() else {}
            yield users
            if len(users) > 128:
                raise ValueError('Account limit is 128')
            descriptor, temporary = tempfile.mkstemp(prefix='.accounts-', dir=self.path.parent)
            try:
                with os.fdopen(descriptor, 'w') as output:
                    json.dump({'version': 1, 'users': users}, output)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, self.path)
                directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
                self.signature = None
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)

    def create(self, name, role, encoded):
        name = username(name)
        if role not in ('operator', 'observer'):
            raise ValueError('Role must be operator or observer')
        hash_parts(encoded)
        with self.edit() as users:
            if name in users:
                raise ValueError('Account already exists; use reset-password explicitly')
            users[name] = {'role': role, 'password_hash': encoded, 'enabled': True, 'revision': secrets.token_hex(16)}

    def update(self, name, **changes):
        name = username(name)
        if set(changes) - {'role', 'password_hash', 'enabled'}:
            raise ValueError('Unsupported account change')
        if 'role' in changes and changes['role'] not in ('operator', 'observer'):
            raise ValueError('Role must be operator or observer')
        if 'password_hash' in changes:
            hash_parts(changes['password_hash'])
        with self.edit() as users:
            if name not in users:
                raise ValueError('Account not found')
            users[name] = {**users[name], **changes, 'revision': secrets.token_hex(16)}


def prompt_password():
    value = getpass.getpass('New password (12–256 characters): ')
    if value != getpass.getpass('Confirm password: '):
        raise ValueError('Passwords differ')
    return make_password_hash(value)


def main():
    parser = argparse.ArgumentParser(description='Private host-administrator account CLI; no signup or HTTP administration')
    parser.add_argument('--store', required=True, help='Absolute private account-store path outside the repository')
    commands = parser.add_subparsers(dest='action', required=True)
    create = commands.add_parser('create')
    create.add_argument('username')
    create.add_argument('--role', required=True, choices=('operator', 'observer'))
    commands.add_parser('list')
    for action in ('disable', 'enable', 'reset-password', 'revoke'):
        commands.add_parser(action).add_argument('username')
    role = commands.add_parser('set-role')
    role.add_argument('username')
    role.add_argument('role', choices=('operator', 'observer'))
    migrate = commands.add_parser('migrate-legacy')
    migrate.add_argument('username')
    migrate.add_argument('--config', required=True, help='Existing private LAN env containing OPERATOR_PASSWORD_HASH')
    args = parser.parse_args()
    try:
        store = AccountStore(args.store)
        if args.action == 'list':
            for name, user in sorted(store.load().items()):
                print(f'{name}\t{user["role"]}\t{"enabled" if user["enabled"] else "disabled"}')
            return
        if args.action == 'create':
            store.create(args.username, args.role, prompt_password())
        elif args.action == 'migrate-legacy':
            from dotenv import dotenv_values
            config = private_file(args.config)
            value = dotenv_values(config, interpolate=False).get('OPERATOR_PASSWORD_HASH', '')
            hash_parts(value)
            store.create(args.username, 'operator', value)
        elif args.action == 'reset-password':
            store.update(args.username, password_hash=prompt_password())
        elif args.action == 'set-role':
            store.update(args.username, role=args.role)
        elif args.action in ('disable', 'enable'):
            store.update(args.username, enabled=args.action == 'enable')
        else:
            store.update(args.username)
        print(f'{args.action}: {username(args.username)}. Account saved; previous sessions for this user are revoked.')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f'ERROR: {exc}') from exc


if __name__ == '__main__':
    main()
