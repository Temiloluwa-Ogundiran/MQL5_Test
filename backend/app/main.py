import hashlib
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from .models import Intent, Report
from .schemas import IntentIn, IntentOut, ReportIn

app = FastAPI()
try:
    Base.metadata.create_all(bind=engine)
except Exception:
    pass


def mk_magic(s):
    return int(hashlib.md5(s.encode()).hexdigest()[:6], 16) % 50000 + 10000


def mk_comment(s):
    return hashlib.md5(s.encode()).hexdigest()[:12]


@app.get("/")
def root():
    return {
        "msg": "MQL5 Execution API running",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/intents", response_model=IntentOut, status_code=201)
def create_intent(data: IntentIn, db: Session = Depends(get_db)):
    gen = datetime.now(timezone.utc)
    # Check idempotency
    row = (
        db.query(Intent)
        .filter_by(signal_id=data.signal_id, account_id=data.account_id)
        .first()
    )
    if row:
        return row
    m = mk_magic(data.signal_id)
    c = mk_comment(data.signal_id)
    payload = data.model_dump()
    payload["generated_at"] = gen
    row = Intent(**payload, magic_number=m, comment=c, status="PENDING")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.get("/intents/next", response_model=IntentOut)
def next_intent(account_id: int, db: Session = Depends(get_db)):
    row = (
        db.query(Intent)
        .filter_by(account_id=account_id, status="PENDING")
        .order_by(Intent.created_at)
        .first()
    )
    if not row:
        raise HTTPException(status_code=204)
    row.status = "SENT"
    row.sent_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


@app.post("/reports", status_code=201)
def create_report(data: ReportIn, db: Session = Depends(get_db)):
    if data.deal_ticket != 0:
        ex = (
            db.query(Report)
            .filter_by(signal_id=data.signal_id, deal_ticket=data.deal_ticket)
            .first()
        )
        if ex:
            return ex
    r = Report(**data.model_dump())
    db.add(r)
    it = (
        db.query(Intent)
        .filter_by(signal_id=data.signal_id, account_id=data.account_id)
        .first()
    )
    if it and it.status in ("PENDING", "SENT"):
        it.status = data.status
    db.commit()
    db.refresh(r)
    return r


@app.get("/intents/{signal_id}")
def get_intent(signal_id: str, db: Session = Depends(get_db)):
    rows = db.query(Intent).filter_by(signal_id=signal_id).all()
    if not rows:
        raise HTTPException(status_code=404, detail="not found")
    return rows


@app.get("/reports")
def get_reports(signal_id: str, db: Session = Depends(get_db)):
    return db.query(Report).filter_by(signal_id=signal_id).all()
