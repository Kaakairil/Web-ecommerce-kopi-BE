"""Event outbox worker: deliver pending events, backoff, dead-letter."""
from unittest.mock import MagicMock

from app.services.event_worker import deliver_pending_events


def make_db(pending, mark_calls=None):
    """Fake supabase-ish db that persists update() into the fetched rows."""
    rows = {e["id"]: dict(e) for e in pending}
    db = MagicMock()

    def update(fields):
        # capture the update target; applied on .execute()
        db._pending_update = dict(fields)
        upd = MagicMock()
        upd.eq.return_value.execute.return_value = None
        return upd

    def table(name):
        t = MagicMock()
        t.update.side_effect = None
        # wire update chains: .update(f).eq(id, x).execute()
        def update_side(fields):
            holder = {}

            def eq(col, val):
                def do_execute():
                    rows[val].update(fields)
                holder["execute"] = do_execute
                eqm = MagicMock()
                eqm.execute.side_effect = do_execute
                return eqm
            m = MagicMock()
            m.eq.side_effect = eq
            return m

        t.update.side_effect = update_side
        t.select.return_value.eq.return_value.execute.return_value.data = list(
            rows.values()
        )
        return t

    db.table.side_effect = table
    return db


def make_event(id=1, payload='{"x":1}', attempts=0):
    return {"id": id, "event_type": "order.created", "payload": payload,
            "attempts": attempts, "status": "pending"}


def test_delivers_after_transient_failures():
    pending = [make_event(id=1)]
    db = make_db(pending)
    results = iter([Exception("boom"), Exception("boom"), Exception("boom"),
                    MagicMock(status_code=200)])
    posts = []

    def fake_post(url, json=None, headers=None, timeout=None):
        posts.append((url, json, headers))
        r = next(results)
        if isinstance(r, Exception):
            raise r
        return r

    stats = deliver_pending_events(db, fake_post, stop_event=None, max_attempts=5,
                                   max_cycles=4)
    assert stats["delivered"] == 1
    assert len(posts) == 4  # 3 failures + 1 success
    assert posts[0][2]["X-KoMa-Signature"]  # signed webhook


def test_five_failures_marks_dead():
    pending = [make_event(id=2, attempts=0)]
    db = make_db(pending)

    def always_fail(url, **kw):
        raise Exception("down")

    # worker records one attempt per cycle; event starts at 0 attempts
    stats = deliver_pending_events(db, always_fail, stop_event=None, max_attempts=5,
                                   max_cycles=5)
    assert stats["dead"] == 1
    assert stats["delivered"] == 0


def test_no_pending_events_no_posts():
    db = make_db([])
    posts = MagicMock()
    stats = deliver_pending_events(db, posts, stop_event=None, max_attempts=5,
                                   max_cycles=1)
    assert stats["delivered"] == 0
    posts.assert_not_called()
