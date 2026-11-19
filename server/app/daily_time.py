from datetime import datetime

from sqlalchemy.dialects.sqlite import insert

from .models import DailyTimeAdjustment


def adjustment_minutes(db, child_id, day):
    adjustment = db.get(DailyTimeAdjustment, (child_id, day))
    return adjustment.minutes if adjustment else 0


def adjust_today(db, child_id, minutes):
    day = datetime.now().date()
    statement = insert(DailyTimeAdjustment).values(
        child_id=child_id, day=day, minutes=minutes,
    )
    db.execute(statement.on_conflict_do_update(
        index_elements=[DailyTimeAdjustment.child_id, DailyTimeAdjustment.day],
        set_={"minutes": DailyTimeAdjustment.minutes + statement.excluded.minutes},
    ))
