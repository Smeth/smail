from types import SimpleNamespace
import sys
import pytest
from mailclient.storage.secrets import Secrets

def test_refuse_plaintext_or_unknown_backend(monkeypatch):
    monkeypatch.setitem(sys.modules, 'keyring', SimpleNamespace(get_keyring=lambda: object()))
    with pytest.raises(RuntimeError, match='Windows'):
        Secrets().set('account', 'secret')

def test_windows_vault_only_and_missing_password(monkeypatch):
    backend = type('WinVaultKeyring', (), {'__module__': 'keyring.backends.Windows'})()
    calls = []
    monkeypatch.setitem(sys.modules, 'keyring', SimpleNamespace(
        get_keyring=lambda: backend,
        set_password=lambda *args: calls.append(args),
        get_password=lambda *args: None))
    Secrets().set('account', 'secret')
    assert calls == [('SmailDesktop', 'account', 'secret')]
    with pytest.raises(RuntimeError, match='absent'):
        Secrets().get('account')
