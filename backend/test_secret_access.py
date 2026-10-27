"""Credential handling tests; no live secrets or network calls."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import secret_access as sa

class SecretAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.credentials = Path(self.temp.name) / 'app.json'
        self.credentials.write_text(json.dumps({'role_id': 'test-role', 'secret_id': 'test-secret'}))
        self.env = patch.dict(os.environ, {
            'VECTOR_SECRET_PROVIDER': 'openbao',
            'OPENBAO_CREDENTIALS_FILE': str(self.credentials),
            'OPENBAO_ADDR': 'http://test.invalid',
        })
        self.env.start(); self.addCleanup(self.env.stop)

    def test_login_and_read_scoped_secret(self):
        def answer(address, path, **kwargs):
            if path == 'auth/approle/login':
                self.assertEqual(kwargs['data'], {'role_id': 'test-role', 'secret_id': 'test-secret'})
                return {'auth': {'client_token': 'test-token'}}
            self.assertEqual(path, 'support/data/vector-db')
            self.assertEqual(kwargs['token'], 'test-token')
            return {'data': {'data': {'password': 'test-password'}}}
        with patch.object(sa, 'request', side_effect=answer) as mock:
            self.assertEqual(sa.read_vector_password(), 'test-password')
            self.assertEqual(mock.call_count, 2)

    def test_no_file_fallback_on_openbao_error(self):
        password = Path(self.temp.name) / 'password'; password.write_text('fallback-secret')
        with patch.dict(os.environ, {'VECTOR_PASSWORD_FILE': str(password)}), \
             patch.object(sa, 'request', side_effect=sa.SecretAccessError('sealed')):
            with self.assertRaises(sa.SecretAccessError): sa.read_vector_password()

    def test_missing_credentials(self):
        self.credentials.unlink()
        with self.assertRaises(sa.SecretAccessError): sa.login()

    def test_placeholder_credentials(self):
        self.credentials.write_text('{}')
        with self.assertRaises(sa.SecretAccessError): sa.login()

    def test_missing_login_token(self):
        with patch.object(sa, 'request', return_value={'auth': {}}):
            with self.assertRaises(sa.SecretAccessError): sa.login()

    def test_missing_secret_value(self):
        with patch.object(sa, 'request', side_effect=[{'auth': {'client_token': 'test'}}, {'data': {'data': {}}}]):
            with self.assertRaises(sa.SecretAccessError): sa.read_vector_password()

    def test_unknown_provider(self):
        with patch.dict(os.environ, {'VECTOR_SECRET_PROVIDER': 'typo'}):
            with self.assertRaises(sa.SecretAccessError): sa.read_vector_password()

    def test_native_file_provider(self):
        password = Path(self.temp.name) / 'password';password.write_text('local-test\n')
        with patch.dict(os.environ, {'VECTOR_SECRET_PROVIDER': 'file', 'VECTOR_PASSWORD_FILE': str(password)}):
            self.assertEqual(sa.read_vector_password(), 'local-test')

    def test_http_errors_do_not_leak_details(self):
        error = urllib.error.HTTPError('http://test.invalid', 403, 'sensitive-body', {}, None)
        with patch.object(sa.urllib.request, 'build_opener') as factory:
            factory.return_value.open.side_effect = error
            with self.assertRaises(sa.SecretAccessError) as caught:
                sa.request('http://test.invalid', 'support/data/vector-db', token='private-token')
        self.assertEqual(str(caught.exception), 'OpenBao request failed (HTTP 403).')
        self.assertTrue(caught.exception.__suppress_context__)

    def test_redirects_are_not_followed(self):
        self.assertIsNone(sa.NoRedirect().redirect_request(None, None, 302, '', {}, 'http://other.invalid'))

if __name__ == '__main__': unittest.main()
