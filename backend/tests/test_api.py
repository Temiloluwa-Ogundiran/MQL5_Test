import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT))

from datetime import datetime, timedelta, timezone  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

try:
    from app.db import Base, get_db  # noqa: E402
    from app.main import app  # noqa: E402
except ImportError:
    from backend.app.db import Base, get_db  # noqa: E402
    from backend.app.main import app  # noqa: E402

# In-memory SQLite for tests
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
Base.metadata.create_all(bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def _reset():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)


def test_models_import():
    try:
        from app.models import Intent  # noqa: F401
    except ImportError:
        from backend.app.models import Intent  # noqa: F401

    assert Intent is not None


def test_post_intent_and_idempotency():
    _reset()
    now = datetime.now(timezone.utc)
    payload = {
        "signal_id": "SIG-IDEM-001",
        "account_id": 12345,
        "symbol": "EURUSD",
        "direction": "BUY",
        "lots": 0.1,
        "sl": 0,
        "tp": 0,
        "generated_at": now.isoformat(),
    }
    r1 = client.post("/intents", json=payload)
    assert r1.status_code == 201, r1.text
    j1 = r1.json()
    assert 10000 <= j1["magic_number"] < 60000
    assert len(j1["comment"]) == 12

    r2 = client.post("/intents", json=payload)
    assert r2.status_code in (200, 201), r2.text
    j2 = r2.json()
    assert j1["signal_id"] == j2["signal_id"]
    assert j1["magic_number"] == j2["magic_number"]
    assert j1["comment"] == j2["comment"]

    # No duplicate via GET
    r3 = client.get(f"/intents/{payload['signal_id']}")
    assert r3.status_code == 200
    assert len(r3.json()) == 1


def test_staleness_reject():
    _reset()
    old = datetime.now(timezone.utc) - timedelta(seconds=400)
    payload = {
        "signal_id": "SIG-STALE-001",
        "account_id": 99999,
        "symbol": "EURUSD",
        "direction": "SELL",
        "lots": 0.1,
        "sl": 0,
        "tp": 0,
        "generated_at": old.isoformat(),
    }
    r = client.post("/intents", json=payload)
    assert r.status_code == 400, r.text

    # Second post returns existing STALE row idempotently.
    # First stale stores then raises 400, second returns row.
    r2 = client.post("/intents", json=payload)
    assert r2.status_code in (200, 201), r2.text
    j2 = r2.json()
    assert j2["status"] == "STALE"

    # GET next should not return stale
    nxt = client.get("/intents/next", params={"account_id": 99999})
    assert nxt.status_code == 204


def test_report_appends_history():
    _reset()
    now = datetime.now(timezone.utc)
    payload = {
        "signal_id": "SIG-REP-001",
        "account_id": 55555,
        "symbol": "EURUSD",
        "direction": "BUY",
        "lots": 0.2,
        "sl": 0,
        "tp": 0,
        "generated_at": now.isoformat(),
    }
    ri = client.post("/intents", json=payload)
    assert ri.status_code == 201

    rep1 = {
        "signal_id": "SIG-REP-001",
        "account_id": 55555,
        "magic": ri.json()["magic_number"],
        "order_ticket": 1001,
        "deal_ticket": 2001,
        "position_ticket": 3001,
        "fill_price": 1.1,
        "filled_volume": 0.2,
        "retcode": 10009,
        "retcode_description": "done",
        "status": "EXECUTED",
    }
    r1 = client.post("/reports", json=rep1)
    assert r1.status_code == 201, r1.text

    # Idempotent on same deal_ticket
    r1dup = client.post("/reports", json=rep1)
    assert r1dup.status_code in (200, 201)
    if "id" in r1dup.json():
        assert r1dup.json()["id"] == r1.json()["id"]

    # Different deal_ticket should append
    rep2 = {**rep1, "deal_ticket": 2002, "order_ticket": 1002}
    r2 = client.post("/reports", json=rep2)
    assert r2.status_code == 201

    # GET reports shows full history (2 rows)
    gr = client.get("/reports", params={"signal_id": "SIG-REP-001"})
    assert gr.status_code == 200
    assert len(gr.json()) == 2

    # Intent status updated
    gi = client.get("/intents/SIG-REP-001")
    assert gi.status_code == 200
    assert gi.json()[0]["status"] == "EXECUTED"


def test_health_and_next():
    _reset()
    h = client.get("/health")
    assert h.status_code == 200 and h.json() == {"ok": True}

    now = datetime.now(timezone.utc)
    p = {
        "signal_id": "SIG-NEXT-001",
        "account_id": 77777,
        "symbol": "EURUSD",
        "direction": "BUY",
        "lots": 0.1,
        "sl": 0,
        "tp": 0,
        "generated_at": now.isoformat(),
    }
    client.post("/intents", json=p)
    nxt = client.get("/intents/next", params={"account_id": 77777})
    assert nxt.status_code == 200
    assert nxt.json()["signal_id"] == "SIG-NEXT-001"
    assert nxt.json()["status"] == "SENT"

    nxt2 = client.get("/intents/next", params={"account_id": 77777})
    assert nxt2.status_code == 204
