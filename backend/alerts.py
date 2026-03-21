import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from sqlalchemy.orm import Session
import models

logger = logging.getLogger(__name__)


def vehicle_matches_alert(v: models.Vehicle, a: models.WatchlistAlert) -> bool:
    if a.make and a.make.lower() not in (v.make or "").lower():
        return False
    if a.model and a.model.lower() not in (v.model or "").lower():
        return False
    if a.max_price is not None and v.price is not None and v.price > a.max_price:
        return False
    if a.min_price is not None and v.price is not None and v.price < a.min_price:
        return False
    if a.max_mileage is not None and v.mileage is not None and v.mileage > a.max_mileage:
        return False
    if a.min_year is not None and v.year is not None and v.year < a.min_year:
        return False
    if a.max_year is not None and v.year is not None and v.year > a.max_year:
        return False
    if a.condition and a.condition.lower() not in (v.condition or "").lower():
        return False
    return True


def get_matching_vehicles(alert: models.WatchlistAlert, db: Session):
    q = db.query(models.Vehicle).filter(models.Vehicle.is_active == True)
    # Scope to specific dealer when alert has a dealer_id set (NULL = all locations)
    if alert.dealer_id is not None:
        q = q.filter(models.Vehicle.dealer_id == alert.dealer_id)
    vehicles = q.all()
    return [v for v in vehicles if vehicle_matches_alert(v, alert)]


def check_and_notify_watchlist(db: Session):
    alerts = db.query(models.WatchlistAlert).filter(
        models.WatchlistAlert.is_active == True
    ).all()
    if not alerts:
        return

    # Vehicles added during the most recent scrape
    latest_log = (
        db.query(models.ScrapeLog)
        .filter(models.ScrapeLog.status == "success")
        .order_by(models.ScrapeLog.timestamp.desc())
        .first()
    )
    if not latest_log:
        return

    recent_additions = (
        db.query(models.Vehicle)
        .filter(
            models.Vehicle.is_active == True,
            models.Vehicle.first_seen >= latest_log.timestamp,
        )
        .all()
    )

    if not recent_additions:
        return

    for alert in alerts:
        matches = [v for v in recent_additions if vehicle_matches_alert(v, alert)]
        if matches:
            alert.last_triggered = datetime.utcnow()
            alert.trigger_count = (alert.trigger_count or 0) + len(matches)
            logger.info(f"Alert '{alert.name}' matched {len(matches)} new vehicle(s)")
            if alert.notification_email:
                _send_email(alert, matches)

    db.commit()


def _send_email(alert: models.WatchlistAlert, vehicles: list):
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")

    if not smtp_user or not smtp_pass:
        logger.info(
            f"Email not configured. Alert '{alert.name}' matched {len(vehicles)} vehicle(s)."
        )
        return

    lines = [
        f"ALM Watchlist Alert: {alert.name}",
        f"Found {len(vehicles)} matching vehicle(s):\n",
    ]
    for v in vehicles:
        lines.append(f"  {v.year} {v.make} {v.model} {v.trim or ''}".strip())
        lines.append(f"  Price: ${v.price:,.0f}" if v.price else "  Price: N/A")
        lines.append(f"  Mileage: {v.mileage:,}" if v.mileage else "  Mileage: N/A")
        lines.append(f"  Stock #: {v.stock_number}")
        if v.listing_url:
            lines.append(f"  Link: {v.listing_url}")
        lines.append("")

    try:
        msg = MIMEMultipart()
        msg["From"] = smtp_user
        msg["To"] = alert.notification_email
        msg["Subject"] = f"[ALM Alert] {alert.name} — {len(vehicles)} match(es)"
        msg.attach(MIMEText("\n".join(lines), "plain"))

        with smtplib.SMTP(smtp_host, smtp_port) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_user, alert.notification_email, msg.as_string())

        logger.info(f"Alert email sent to {alert.notification_email}")
    except Exception as e:
        logger.error(f"Failed to send alert email: {e}")
