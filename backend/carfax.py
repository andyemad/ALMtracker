from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

import models
from scraper import BASE_URL, HEADERS

logger = logging.getLogger(__name__)

CARFAX_URL_RE = re.compile(r"https?://(?:www\.)?carfax\.com/[^\s\"'<>]+", re.IGNORECASE)


@dataclass
class CarfaxResolution:
    carfax_url: str
    listing_url: str
    source_url: str


def _clean_carfax_url(value: str | None) -> Optional[str]:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    if value.startswith("//"):
        return f"https:{value}"
    if value.startswith("/"):
        return f"{BASE_URL}{value}"
    if value.lower().startswith("http"):
        return value
    return None


def _find_carfax_url(node: Any) -> Optional[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if "carfax" in key.lower() and isinstance(value, str):
                cleaned = _clean_carfax_url(value)
                if cleaned:
                    return cleaned
        for value in node.values():
            found = _find_carfax_url(value)
            if found:
                return found
        return None

    if isinstance(node, list):
        for item in node:
            found = _find_carfax_url(item)
            if found:
                return found
        return None

    if isinstance(node, str) and "carfax.com" in node.lower():
        match = CARFAX_URL_RE.search(node)
        return _clean_carfax_url(match.group(0)) if match else _clean_carfax_url(node)

    return None


def _extract_carfax_url(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", {"id": "__NEXT_DATA__"})
    if script:
        raw = script.string or script.get_text(strip=False)
        if raw:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Failed to decode __NEXT_DATA__ while extracting CARFAX URL")
            else:
                found = _find_carfax_url(payload)
                if found:
                    return found

    match = CARFAX_URL_RE.search(html)
    return _clean_carfax_url(match.group(0)) if match else None


def _candidate_listing_urls(vehicle: models.Vehicle) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    for raw in (
        vehicle.listing_url,
        f"{BASE_URL}/inventory/{vehicle.stock_number.lower()}" if vehicle.stock_number else None,
        f"{BASE_URL}/inventory/{vehicle.vin}" if vehicle.vin else None,
    ):
        if not raw:
            continue
        candidate = raw.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        candidates.append(candidate)

    return candidates


def resolve_vehicle_carfax(
    db: Session,
    vehicle: models.Vehicle,
    *,
    force_refresh: bool = False,
) -> CarfaxResolution:
    if vehicle.carfax_url and not force_refresh:
        return CarfaxResolution(
            carfax_url=vehicle.carfax_url,
            listing_url=vehicle.listing_url or "",
            source_url=vehicle.listing_url or "",
        )

    candidates = _candidate_listing_urls(vehicle)
    if not candidates:
        raise LookupError("Vehicle does not have a listing URL, stock number, or VIN to resolve a CARFAX")

    last_error: Exception | None = None

    with httpx.Client(follow_redirects=True, timeout=20.0, headers=HEADERS) as client:
        for source_url in candidates:
            try:
                response = client.get(source_url)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning("CARFAX lookup failed for %s: %s", source_url, exc)
                continue

            carfax_url = _extract_carfax_url(response.text)
            if not carfax_url:
                logger.info("No CARFAX URL found on listing page %s", response.url)
                continue

            vehicle.carfax_url = carfax_url
            vehicle.carfax_fetched_at = datetime.utcnow()
            vehicle.listing_url = str(response.url)
            db.add(vehicle)
            db.commit()
            db.refresh(vehicle)

            return CarfaxResolution(
                carfax_url=carfax_url,
                listing_url=vehicle.listing_url or str(response.url),
                source_url=source_url,
            )

    if last_error:
        raise LookupError("Could not load the ALM listing to find the CARFAX link") from last_error

    raise LookupError("No CARFAX link was found on the ALM listing for that vehicle")
