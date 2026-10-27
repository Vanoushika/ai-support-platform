"""Read-only live checks. Never prints secrets or access tokens."""
import os
from pathlib import Path
from secret_access import SECRET_PATH, login, request, read_vector_password
from vector_store import connect

def main():
    if os.getenv('VECTOR_SECRET_PROVIDER') != 'openbao':
        raise SystemExit('FAIL: expected OpenBao secret provider.')
    if Path('/run/secrets/vector_password').exists():
        raise SystemExit('FAIL: direct database password is still mounted in the app.')
    address, token = login()
    data = request(address, 'sys/capabilities-self', token=token,
                   data={'paths': [SECRET_PATH, 'support/data/unrelated', 'sys/mounts']})
    capabilities = data.get('data', data)
    if set(capabilities.get(SECRET_PATH, [])) != {'read'}:
        raise SystemExit('FAIL: database-secret permissions must be read-only.')
    for path in ['support/data/unrelated', 'sys/mounts']:
        if capabilities.get(path) != ['deny']:
            raise SystemExit('FAIL: unrelated-secret or administrator access is not denied.')
    print('PASS: AppRole has read-only access to the database-secret path.')
    print('PASS: unrelated secrets and mount administration are denied.')
    read_vector_password()
    with connect() as conn:
        conn.execute('SELECT 1').fetchone()
    print('PASS: PostgreSQL connection uses the OpenBao-provided password.')
    print('PASS: direct password file is absent from this app container.')

if __name__ == '__main__':
    main()
