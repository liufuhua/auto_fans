from datetime import datetime, timedelta, timezone


BEIJING_TZ = timezone(timedelta(hours=8))


def now_beijing() -> datetime:
    return datetime.now(BEIJING_TZ).replace(tzinfo=None)
