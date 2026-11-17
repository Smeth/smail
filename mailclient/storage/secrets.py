"""Secrets exclusivement dans le coffre système ; aucun repli fichier."""
from uuid import uuid4

class Secrets:
    SERVICE = 'SmailDesktop'
    PREFIX = '@SMAIL-CHUNKS-v1:'

    def _backend(self):
        import keyring
        backend = keyring.get_keyring()
        if not type(backend).__module__.startswith('keyring.backends.Windows'):
            raise RuntimeError('Le Gestionnaire d’identifiants Windows est requis pour stocker les mots de passe.')
        return keyring

    def get(self, account_id: str) -> str:
        value = self._backend().get_password(self.SERVICE, account_id)
        if value is None:
            raise RuntimeError('Mot de passe absent du Gestionnaire d’identifiants Windows.')
        if value.startswith(self.PREFIX):
            try:
                generation, count = value[len(self.PREFIX):].split(':')
                if not 1 <= int(count) <= 1000:
                    raise ValueError()
                chunks = [self._backend().get_password(self.SERVICE, f'{account_id}:{generation}:{i}') for i in range(int(count))]
                if any(chunk is None for chunk in chunks):
                    raise ValueError()
                value = ''.join(chunks)
            except (ValueError, TypeError):
                raise RuntimeError('Secret incomplet dans le coffre Windows. Reconnectez ce compte.') from None
        return value

    def delete(self, account_id: str) -> None:
        """Supprime un secret et ses fragments ; un secret déjà absent n’est pas une erreur."""
        backend = self._backend()
        value = backend.get_password(self.SERVICE, account_id)
        if value is None:
            return
        if value.startswith(self.PREFIX):
            try:
                generation, count = value[len(self.PREFIX):].split(':')
                for i in range(min(int(count), 1000)):
                    try:
                        backend.delete_password(self.SERVICE, f'{account_id}:{generation}:{i}')
                    except Exception:
                        pass  # Fragment déjà absent.
            except ValueError:
                pass
        backend.delete_password(self.SERVICE, account_id)

    def set(self, account_id: str, password: str) -> None:
        backend = self._backend()
        old = backend.get_password(self.SERVICE, account_id)
        if len(password) > 500 or password.startswith(self.PREFIX):
            generation = uuid4().hex
            chunks = [password[i:i+500] for i in range(0, len(password), 500)]
            if len(chunks) > 1000:
                raise ValueError('Secret trop volumineux pour le coffre Windows.')
            for i, chunk in enumerate(chunks):
                backend.set_password(self.SERVICE, f'{account_id}:{generation}:{i}', chunk)
            backend.set_password(self.SERVICE, account_id, f'{self.PREFIX}{generation}:{len(chunks)}')
        else:
            backend.set_password(self.SERVICE, account_id, password)
        if old and old.startswith(self.PREFIX):
            try:
                generation, count = old[len(self.PREFIX):].split(':')
                for i in range(min(int(count), 1000)):
                    backend.delete_password(self.SERVICE, f'{account_id}:{generation}:{i}')
            except Exception:
                pass  # Le nouveau secret est déjà atomiquement référencé.
