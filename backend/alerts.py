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

    # Build HTML email
    vehicle_rows = ""
    for v in vehicles:
        price_str = f"${v.price:,.0f}" if v.price else "N/A"
        mileage_str = f"{v.mileage:,} mi" if v.mileage else "N/A"
        link = v.listing_url or f"https://www.almcars.com/inventory/{(v.stock_number or '').lower()}"
        location = v.location_name or ""
        vehicle_rows += f"""
        <tr style="border-bottom:1px solid #334155;">
          <td style="padding:12px 8px;">
            <strong>{v.year} {v.make} {v.model}</strong>
            {f'<br><span style="color:#94a3b8;font-size:13px;">{v.trim}</span>' if v.trim else ''}
            {f'<br><span style="color:#64748b;font-size:12px;">{location}</span>' if location else ''}
          </td>
          <td style="padding:12px 8px;font-weight:600;">{price_str}</td>
          <td style="padding:12px 8px;color:#94a3b8;">{mileage_str}</td>
          <td style="padding:12px 8px;">
            <a href="{link}" style="color:#818cf8;text-decoration:none;">View Listing &rarr;</a>
          </td>
        </tr>"""

    html = f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:600px;margin:0 auto;background:#0f172a;color:#e2e8f0;padding:24px;border-radius:12px;">
      <h2 style="color:#818cf8;margin:0 0 4px;">ALM Watchlist Alert</h2>
      <p style="color:#94a3b8;margin:0 0 20px;font-size:14px;">
        Your alert <strong style="color:#e2e8f0;">{alert.name}</strong> matched
        <strong style="color:#22c55e;">{len(vehicles)}</strong> new vehicle(s).
      </p>
      <table style="width:100%;border-collapse:collapse;font-size:14px;color:#e2e8f0;">
        <thead>
          <tr style="border-bottom:2px solid #334155;text-align:left;">
            <th style="padding:8px;color:#64748b;font-weight:600;">Vehicle</th>
            <th style="padding:8px;color:#64748b;font-weight:600;">Price</th>
            <th style="padding:8px;color:#64748b;font-weight:600;">Mileage</th>
            <th style="padding:8px;color:#64748b;font-weight:600;">Link</th>
          </tr>
        </thead>
        <tbody>{vehicle_rows}</tbody>
      </table>
      <p style="color:#475569;font-size:12px;margin:20px 0 0;border-top:1px solid #1e293b;padding-top:16px;">
        ALM Inventory Tracker &middot; This alert runs automatically every 6 hours.
        <br>To stop receiving these emails, disable or delete the alert on your dashboard.
      </p>
    </div>
    """

    # Plain text fallback
    plain_lines = [f"ALM Watchlist Alert: {alert.name}", f"Found {len(vehicles)} matching vehicle(s):\n"]
    for v in vehicles:
        plain_lines.append(f"  {v.year} {v.make} {v.model} {v.trim or ''}".strip())
        plain_lines.append(f"  Price: ${v.price:,.0f}" if v.price else "  Price: N/A")
        plain_lines.append(f"  Mileage: {v.mileage:,}" if v.mileage else "  Mileage: N/A")
        plain_lines.append(f"  Stock #: {v.stock_number}")
        if v.listing_url:
            plain_lines.append(f"  Link: {v.listing_url}")
        plain_lines.append("")

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"ALM Tracker <{smtp_user}>"
        msg["To"] = alert.notification_email
        msg["Subject"] = f"[ALM Alert] {alert.name} — {len(vehicles)} match(es)"
        msg.attach(MIMEText("\n".join(plain_lines), "plain"))
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(smtp_host, smtp_port) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_user, alert.notification_email, msg.as_string())

        logger.info(f"Alert email sent to {alert.notification_email}")
    except Exception as e:
        logger.error(f"Failed to send alert email: {e}")
