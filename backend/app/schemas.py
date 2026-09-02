from datetime import datetime

from pydantic import BaseModel, ConfigDict


class IntentIn(BaseModel):
    signal_id: str
    account_id: int
    symbol: str
    direction: str
    lots: float
    sl: float = 0
    tp: float = 0
    generated_at: datetime


class IntentOut(IntentIn):
    magic_number: int
    comment: str
    status: str

    model_config = ConfigDict(from_attributes=True)


class ReportIn(BaseModel):
    signal_id: str
    account_id: int
    magic: int
    order_ticket: int = 0
    deal_ticket: int = 0
    position_ticket: int = 0
    fill_price: float = 0
    filled_volume: float = 0
    retcode: int = 0
    retcode_description: str = ""
    status: str
