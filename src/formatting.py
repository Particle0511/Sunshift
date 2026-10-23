
from datetime import datetime
from typing import Optional


def indian_number(x: float) -> str:
   
    n = int(round(abs(x)))
    s = str(n)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return ("-" if x < 0 and n else "") + s


def inr(x: float) -> str:
    return "₹" + indian_number(x)


def describe_start(start_dt: datetime, now: Optional[datetime] = None) -> str:
    
    if now is None:
        from src.config import now_ist
        now = now_ist()
    clock = start_dt.strftime("%I %p").lstrip("0")
    days = (start_dt.date() - now.date()).days
    if days <= 0:
        return f"today at {clock}"
    if days == 1:
        return f"tomorrow at {clock}"
    return f"on {start_dt.strftime('%A')} at {clock}"