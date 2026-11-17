"""Réserve de sessions IMAP et téléchargements groupés."""
import threading
from mailclient.core.accounts import Account, Server
from mailclient.core.imap_client import IMAPClient, ConnectionPool, fetch_items


ACCOUNT = Account('T', 't@example.com', Server('imap.example.com', 993), Server('smtp.example.com', 465))

def account():
    return ACCOUNT


class FakeSession:
    def __init__(self, healthy=True):
        self.healthy, self.closed, self.capabilities = healthy, False, (b'IMAP4REV1',)
        self.fetches = []

    def noop(self):
        if not self.healthy:
            raise OSError('coupé')
        return 'OK', [b'']

    def shutdown(self):
        self.closed = True

    def list(self):
        return 'OK', [b'(\\HasNoChildren) "/" "INBOX"']

    def select(self, folder, readonly=True):
        return 'OK', [b'60']

    def response(self, name):
        return name, [b'7']

    def uid(self, command, *args):
        if command == 'search':
            return 'OK', [b' '.join(str(i).encode() for i in range(1, 61))]
        self.fetches.append(args)
        response = []
        for n, uid in enumerate(args[0].split(','), 1):
            if 'BODY.PEEK[]' in args[1]:
                response += [(b'%d (UID %s FLAGS (\\Seen) BODY[] {10}' % (n, uid.encode()), b'Subject: ' + uid.encode() + b'\r\n\r\n'), b')']
            else:
                response.append(b'%d (UID %s FLAGS (\\Flagged))' % (n, uid.encode()))
        return 'OK', response


def pooled_client(pool, sessions, password='pw'):
    client = IMAPClient(account(), password, None, pool)
    def open_session():
        session = FakeSession()
        sessions.append(session)
        return session
    client.open = open_session
    return client


def test_pool_reuses_authenticated_session():
    pool, sessions = ConnectionPool(), []
    client = pooled_client(pool, sessions)
    client.folders()
    client.folders()
    pooled_client(pool, sessions).folders()
    assert len(sessions) == 1


def test_pool_isolates_changed_credentials_and_discards_after_error():
    pool, sessions = ConnectionPool(), []
    pooled_client(pool, sessions).folders()
    pooled_client(pool, sessions, password='autre').folders()
    assert len(sessions) == 2
    client = pooled_client(pool, sessions)
    client.select = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('refus'))
    try:
        client.messages('INBOX', 0)
    except RuntimeError:
        pass
    assert sessions[0].closed  # Une session ayant échoué n’est jamais rendue à la réserve.
    pooled_client(pool, sessions).folders()
    assert len(sessions) == 3


def test_pool_drops_dead_and_expired_sessions():
    pool = ConnectionPool(ttl=60)
    dead, fresh = FakeSession(healthy=False), FakeSession()
    pool.release('k', dead)
    assert pool.acquire('k') is None and dead.closed
    pool.release('k', fresh)
    pool.idle['k'][0] = (fresh, -10_000)
    assert pool.acquire('k') is None and fresh.closed


def test_pool_clear_by_account_and_limit():
    pool = ConnectionPool(per_key=1)
    a, b, extra = FakeSession(), FakeSession(), FakeSession()
    pool.release(('acc-a', 'x'), a)
    pool.release(('acc-a', 'x'), extra)
    assert extra.closed  # Au-delà de la limite, la session est fermée.
    pool.release(('acc-b', 'x'), b)
    pool.clear('acc-a')
    assert a.closed and not b.closed
    assert pool.acquire(('acc-b', 'x')) is b


def test_snapshot_batches_and_skips_cached_bodies():
    pool, sessions = ConnectionPool(), []
    client = pooled_client(pool, sessions)
    cache = {str(uid): b'Subject: cached\r\n\r\n' for uid in range(51, 61)}
    rows, total, bodies, validity = client.snapshot('INBOX', 40, threading.Event(), lambda uid, v: cache.get(uid))
    fetches = sessions[0].fetches
    assert total == 60 and validity == '7' and len(rows) == 40
    assert [row['uid'] for row in rows] == [str(i) for i in range(60, 20, -1)]
    assert fetches[0] == (','.join(str(i) for i in range(60, 50, -1)), '(UID FLAGS)')
    assert [len(args[0].split(',')) for args in fetches[1:]] == [25, 5]
    assert all(args[1] == '(UID FLAGS BODY.PEEK[])' for args in fetches[1:])
    assert rows[0]['subject'] == 'cached' and rows[0]['starred'] and rows[0]['unread']
    assert rows[10]['subject'] == '50' and not rows[10]['unread']
    assert bodies['60'] == cache['60']


def test_snapshot_stops_when_cancelled():
    pool, sessions = ConnectionPool(), []
    cancelled = threading.Event()
    cancelled.set()
    rows, *_ = pooled_client(pool, sessions).snapshot('INBOX', 40, cancelled)
    assert rows == [] and sessions[0].fetches == []


def test_fetch_items_handles_flags_after_literal():
    parts = [(b'1 (UID 9 BODY[] {3}', b'abc'), b' FLAGS (\\Seen))', b'2 (UID 10 FLAGS ())', b'3 (FLAGS (\\Deleted))']
    items = fetch_items(parts)
    assert set(items) == {'9', '10'}
    assert b'\\Seen' in items['9'][0] and items['9'][1] == b'abc'
    assert items['10'][1] is None
