"""Small synchronous OpenBao client, called from vector-store worker threads."""
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

SECRET_PATH = 'support/data/vector-db'

class SecretAccessError(RuntimeError):
    pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(address, path, *, data=None, token=None, method=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['X-Vault-Token'] = token
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(address.rstrip('/') + '/v1/' + path,
                                 data=body, headers=headers, method=method)
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=10) as response:
            raw = response.read()
        return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        # Never print response bodies, credentials, request payloads or tokens.
        raise SecretAccessError(f'OpenBao request failed (HTTP {exc.code}).') from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise SecretAccessError('OpenBao is unavailable or returned invalid data.') from None


def login():
    address = os.getenv('OPENBAO_ADDR', 'http://openbao:8200')
    path = os.getenv('OPENBAO_CREDENTIALS_FILE', '/run/secrets/bao_app_credentials')
    try:
        credentials = json.loads(Path(path).read_text())
        payload = {key: credentials[key] for key in ('role_id', 'secret_id')}
        if not all(isinstance(v, str) and v for v in payload.values()):
            raise ValueError()
    except (OSError, ValueError, KeyError, TypeError):
        raise SecretAccessError('AppRole credentials are missing. Run setup_openbao.py bootstrap on the host.') from None
    result = request(address, 'auth/approle/login', data=payload)
    token = result.get('auth', {}).get('client_token')
    if not isinstance(token, str) or not token:
        raise SecretAccessError('OpenBao login did not return a token.')
    return address, token


def read_vector_password():
    provider = os.getenv('VECTOR_SECRET_PROVIDER', 'file')
    if provider == 'file':
        path = os.getenv('VECTOR_PASSWORD_FILE')
        if not path:
            raise SecretAccessError('VECTOR_PASSWORD_FILE is not configured.')
        try:
            password = Path(path).read_text().strip()
        except OSError:
            raise SecretAccessError('Cannot read vector password file.') from None
    elif provider == 'openbao':
        address, token = login()
        result = request(address, SECRET_PATH, token=token)
        password = result.get('data', {}).get('data', {}).get('password')
    else:
        raise SecretAccessError('Unknown VECTOR_SECRET_PROVIDER.')
    if not isinstance(password, str) or not password:
        raise SecretAccessError('Vector password is missing or empty.')
    return password
