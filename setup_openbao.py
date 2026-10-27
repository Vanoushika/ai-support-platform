"""Local demo bootstrap. Run on the Mac; never paste the private output files."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'backend'))
from secret_access import request, SecretAccessError

ADDRESS = 'http://127.0.0.1:8201'
PRIVATE = ROOT / '.local-secrets'
ADMIN = PRIVATE / 'bao-bootstrap.json'
APP = PRIVATE / 'bao-app.json'


def save(path, value, mode):
    temp = path.with_suffix('.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    temp.chmod(mode)
    temp.replace(path)


def prepare():
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    PRIVATE.chmod(0o700)
    if not (PRIVATE / 'vector_password').is_file():
        raise RuntimeError('Existing PostgreSQL password file is missing. Stop and restore it before proceeding.')
    if not APP.exists():
        save(APP, {}, 0o644)
    print('Local credential paths prepared; existing credentials preserved.')


def unseal():
    if not ADMIN.is_file():
        raise RuntimeError('No bootstrap credentials found. Run the bootstrap command first.')
    admin = json.loads(ADMIN.read_text())
    status = request(ADDRESS, 'sys/seal-status')
    if status.get('sealed'):
        status = request(ADDRESS, 'sys/unseal', data={'key': admin['keys_base64'][0]})
    if status.get('sealed'):
        raise RuntimeError('OpenBao remains sealed. Preserve the volume and bootstrap file.')
    print('OpenBao is unsealed. No secret values were printed.')
    return admin


def bootstrap():
    prepare()
    initialized = request(ADDRESS, 'sys/init').get('initialized')
    if not initialized:
        if ADMIN.exists():
            raise RuntimeError('OpenBao is uninitialized but a recovery file already exists. Restore the matching volume; nothing overwritten.')
        result = request(ADDRESS, 'sys/init', method='PUT',
                         data={'secret_shares': 1, 'secret_threshold': 1})
        # Save immediately: initialization cannot be undone or repeated safely.
        save(ADMIN, result, 0o600)
    admin = unseal()
    token = admin['root_token']
    def call(path, **kwargs):
        return request(ADDRESS, path, token=token, **kwargs)
    mounts = call('sys/mounts')['data']
    if 'support/' not in mounts:
        call('sys/mounts/support', data={'type': 'kv', 'options': {'version': '2'}})
    elif mounts['support/']['type'] != 'kv' or str(mounts['support/'].get('options', {}).get('version')) != '2':
        raise RuntimeError('Existing support mount is not KV v2; no migration attempted.')
    password = (PRIVATE / 'vector_password').read_text().strip()
    if not password:
        raise RuntimeError('Existing database password file is empty.')
    try:
        existing = call('support/data/vector-db')['data']['data']['password']
    except SecretAccessError as exc:
        if 'HTTP 404' not in str(exc):
            raise
        call('support/data/vector-db', data={'options': {'cas': 0}, 'data': {'password': password}})
    else:
        if existing != password:
            raise RuntimeError('Stored password differs from the existing file. No password was changed.')
    call('sys/policies/acl/support-reader', method='PUT',
         data={'policy': (ROOT / 'openbao/support-reader.hcl').read_text()})
    auth = call('sys/auth')['data']
    if 'approle/' not in auth:
        call('sys/auth/approle', data={'type': 'approle'})
    elif auth['approle/']['type'] != 'approle':
        raise RuntimeError('Existing approle mount has an unexpected type.')
    call('auth/approle/role/support-reader', data={
        'bind_secret_id': True,
        'secret_id_ttl': 0, 'secret_id_num_uses': 0,
        'token_policies': ['support-reader'], 'token_no_default_policy': True,
        'token_type': 'batch', 'token_ttl': '2m', 'token_max_ttl': '2m',
    })
    credentials = json.loads(APP.read_text())
    if not credentials:
        role = call('auth/approle/role/support-reader/role-id')['data']['role_id']
        secret = call('auth/approle/role/support-reader/secret-id', data={})['data']['secret_id']
        credentials = {'role_id': role, 'secret_id': secret}
        save(APP, credentials, 0o644)
    # Prove scoped credentials work without printing them or the password.
    scoped = request(ADDRESS, 'auth/approle/login', data=credentials)['auth']['client_token']
    actual = request(ADDRESS, 'support/data/vector-db', token=scoped)['data']['data']['password']
    if actual != password:
        raise RuntimeError('AppRole secret verification failed.')
    print('PASS: AppRole can read the existing PostgreSQL secret.')
    print('Bootstrap complete. Administrator credentials remain on the host only.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['prepare', 'bootstrap', 'unseal'])
    args = parser.parse_args()
    try:
        {'prepare': prepare, 'bootstrap': bootstrap, 'unseal': unseal}[args.command]()
    except (SecretAccessError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from None
    except (OSError, ValueError, KeyError, TypeError):
        raise SystemExit('Setup could not read expected configuration or credentials. Preserve the private files and report this message.') from None

if __name__ == '__main__':
    main()
