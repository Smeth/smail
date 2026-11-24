"""Mises à jour automatiques depuis les publications GitHub (Releases) de Smail.

Chaîne de confiance : la publication contient un manifeste (version, fichier, SHA-256, taille) signé en
Ed25519 par la CI avec une clé privée gardée dans les secrets du dépôt. Smail n’installe un fichier que si
la signature du manifeste est valide avec la clé publique ci-dessous ET si l’empreinte du fichier téléchargé
correspond. Une publication modifiée à la main, ou un fichier altéré en route, est donc refusé.

Aucune donnée personnelle n’est envoyée : une requête anonyme vers l’API publique de GitHub."""
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

REPOSITORY = 'Smeth/smail'
LATEST = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
PUBLIC_KEY = bytes.fromhex('c87cc05c11bd348482923ceb030597b27189e20d4b9c60373275e16ebbb9c174')
MANIFEST, SIGNATURE = 'smail-update.json', 'smail-update.json.sig'
# Hôtes de GitHub servant l’API et les fichiers des publications (après redirection).
HOSTS = {'api.github.com', 'github.com', 'objects.githubusercontent.com', 'release-assets.githubusercontent.com'}
MAX_INSTALLER = 600 * 1024 * 1024
USER_AGENT = 'Smail-Updater'
VERSION = re.compile(r'(\d{1,4})\.(\d{1,4})\.(\d{1,4})')
INSTALLER_NAME = re.compile(r'Smail-\d{1,4}\.\d{1,4}\.\d{1,4}-installation\.exe')


class UpdateError(RuntimeError):
    pass


@dataclass
class Update:
    version: str
    url: str
    file: str
    sha256: str
    size: int
    notes: str = ''


def parse_version(text: str) -> tuple:
    match = VERSION.fullmatch((text or '').strip().removeprefix('v'))
    if not match:
        raise UpdateError(f'Numéro de version invalide : {text!r}')
    return tuple(int(part) for part in match.groups())


def newer(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)


def checked_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in HOSTS:
        raise UpdateError('Adresse de téléchargement inattendue : mise à jour refusée.')
    return url


def fetch(url: str, limit: int, accept='application/octet-stream', opener=None) -> bytes:
    request = urllib.request.Request(checked_url(url), headers={'User-Agent': USER_AGENT, 'Accept': accept})
    with (opener or urllib.request.urlopen)(request, timeout=30) as response:
        checked_url(response.geturl())  # Redirections comprises.
        data = response.read(limit + 1)
    if len(data) > limit:
        raise UpdateError('Réponse trop volumineuse : mise à jour refusée.')
    return data


def verify_manifest(data: bytes, signature: bytes, public_key: bytes = PUBLIC_KEY) -> dict:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, data)
    except (InvalidSignature, ValueError):
        raise UpdateError('Signature de la mise à jour invalide : elle n’est pas installée.') from None
    manifest = json.loads(data.decode('utf-8'))
    if not isinstance(manifest, dict):
        raise UpdateError('Manifeste de mise à jour invalide.')
    parse_version(manifest.get('version', ''))
    if not INSTALLER_NAME.fullmatch(str(manifest.get('file', ''))):
        raise UpdateError('Nom de fichier de mise à jour inattendu.')
    if not re.fullmatch(r'[0-9a-f]{64}', str(manifest.get('sha256', ''))):
        raise UpdateError('Empreinte de mise à jour invalide.')
    if not isinstance(manifest.get('size'), int) or not 0 < manifest['size'] <= MAX_INSTALLER:
        raise UpdateError('Taille de mise à jour invalide.')
    return manifest


def check(current: str, opener=None, public_key: bytes = PUBLIC_KEY) -> Update | None:
    """Dernière publication si elle est plus récente que `current` et correctement signée ; sinon None."""
    release = json.loads(fetch(LATEST, 1024 * 1024, 'application/vnd.github+json', opener))
    if release.get('draft') or release.get('prerelease'):
        return None
    tag = str(release.get('tag_name', ''))
    if not newer(tag, current):
        return None
    assets = {asset.get('name'): asset.get('browser_download_url') for asset in release.get('assets', [])
              if isinstance(asset, dict)}
    if MANIFEST not in assets or SIGNATURE not in assets:
        raise UpdateError(f'La version {tag} n’est pas signée : elle n’est pas installée automatiquement.')
    data = fetch(assets[MANIFEST], 64 * 1024, opener=opener)
    manifest = verify_manifest(data, fetch(assets[SIGNATURE], 1024, opener=opener), public_key)
    if parse_version(manifest['version']) != parse_version(tag):
        raise UpdateError('La version signée ne correspond pas à la publication.')
    if manifest['file'] not in assets:
        raise UpdateError('Fichier d’installation absent de la publication.')
    return Update(manifest['version'], checked_url(assets[manifest['file']]), manifest['file'], manifest['sha256'],
                  manifest['size'], str(release.get('body') or '')[:4000])


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def download(update: Update, directory: Path, opener=None, cancelled=lambda: False) -> Path:
    """Télécharge l’installateur et vérifie taille et SHA-256 ; un fichier déjà vérifié est réutilisé."""
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / update.file
    if target.exists() and target.stat().st_size == update.size and file_digest(target) == update.sha256:
        return target
    partial = target.with_suffix('.part')
    digest, size = hashlib.sha256(), 0
    request = urllib.request.Request(checked_url(update.url), headers={'User-Agent': USER_AGENT, 'Accept': 'application/octet-stream'})
    try:
        with (opener or urllib.request.urlopen)(request, timeout=60) as response, open(partial, 'wb') as stream:
            checked_url(response.geturl())
            while block := response.read(1 << 16):
                if cancelled():
                    raise UpdateError('Téléchargement interrompu.')
                size += len(block)
                if size > update.size:
                    raise UpdateError('Fichier de mise à jour plus gros qu’annoncé : refusé.')
                digest.update(block)
                stream.write(block)
        if size != update.size or digest.hexdigest() != update.sha256:
            raise UpdateError('Fichier de mise à jour altéré (empreinte différente) : refusé.')
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)
    for old in directory.glob('Smail-*-installation.exe'):  # Anciennes versions téléchargées.
        if old != target:
            old.unlink(missing_ok=True)
    return target


APPMODEL_ERROR_NO_PACKAGE = 15700


def packaged() -> bool:
    """Vrai pour Smail installé depuis le Microsoft Store (paquet MSIX) : le Store gère alors les mises à jour."""
    try:
        import ctypes
        length = ctypes.c_uint32(0)
        return ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(length), None) != APPMODEL_ERROR_NO_PACKAGE
    except (AttributeError, OSError):
        return False  # Hors Windows ou Windows trop ancien : jamais un paquet.


def installed_copy() -> bool:
    """Vrai pour Smail installé par l’installateur (et non lancé depuis les sources, un dossier copié ou le Store)."""
    if not getattr(sys, 'frozen', False) or packaged():
        return False
    folder = Path(sys.executable).parent
    return any(folder.glob('unins*.exe'))


def install(installer: Path, relaunch: bool) -> None:
    """Lance l’installateur en silence, détaché : Smail doit se fermer juste après.

    /CLOSEAPPLICATIONS ferme Smail s’il tourne encore ; /RELAUNCH=1 relance Smail à la fin (voir Smail.iss)."""
    arguments = [str(installer), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NOCANCEL', '/CLOSEAPPLICATIONS',
                 f'/RELAUNCH={1 if relaunch else 0}']
    flags = getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    subprocess.Popen(arguments, creationflags=flags, close_fds=True)
