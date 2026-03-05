import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.database import SessionLocal
from app import crud

logger = logging.getLogger(__name__)


def process_pending_orders():
    """
    Background job executed every 5 minutes.
    Opens its own DB session (separate from request sessions),
    promotes all PENDING orders to PROCESSING, then closes the session.
    This simulates a real fulfillment pipeline where orders are picked
    up by a warehouse system shortly after being placed.
    """
    db = SessionLocal()
    try:
        count = crud.promote_pending_orders(db)
        if count > 0:
            logger.info(f"[Scheduler] Promoted {count} PENDING order(s) to PROCESSING.")
        else:
            logger.info("[Scheduler] No PENDING orders to process.")
    except Exception as e:
        logger.error(f"[Scheduler] Error promoting orders: {e}")
    finally:
        db.close()  # Always close the session to avoid connection leaks


def start_scheduler() -> BackgroundScheduler:
    """
    Initialise and start the APScheduler background scheduler.
    Called once during application startup (see main.py lifespan).
    Returns the scheduler instance so it can be shut down cleanly on exit.
    """
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        process_pending_orders,
        trigger=IntervalTrigger(minutes=5),
        id="process_pending_orders",
        name="Promote PENDING orders to PROCESSING every 5 minutes",
        replace_existing=True,  # Safe to call start_scheduler again without duplicating jobs
    )
    scheduler.start()
    logger.info("[Scheduler] Started. Pending orders will be promoted every 5 minutes.")
    return scheduler
