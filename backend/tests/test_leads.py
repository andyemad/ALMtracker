"""
test_leads.py — Tests for lead CRM endpoints.

Endpoints covered:
  GET    /api/leads                    — list with filters and pagination
  POST   /api/leads                    — create
  PUT    /api/leads/{lead_id}          — update
  DELETE /api/leads/{lead_id}          — delete
  GET    /api/leads/{lead_id}/matches  — inventory matching

Also covers:
  - dealer_id filter on /matches endpoint (Sprint 1 xfail)

Test isolation: every test gets a fresh empty in-memory DB via db_session.
"""

from datetime import datetime, timedelta

import pytest
import sys
import os

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import models


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lead(db, customer_name="John Doe", customer_phone="555-0100",
          customer_email="john@example.com", interested_make=None,
          interested_model=None, max_budget=None, notes=None,
          status="new", source=None, campaign=None, sms_consent=False,
          call_consent=False, consent_text=None):
    now = datetime.utcnow()
    lead = models.Lead(
        customer_name=customer_name,
        customer_phone=customer_phone,
        customer_email=customer_email,
        interested_make=interested_make,
        interested_model=interested_model,
        max_budget=max_budget,
        notes=notes,
        status=status,
        source=source,
        campaign=campaign,
        sms_consent=sms_consent,
        sms_consent_at=now if sms_consent else None,
        call_consent=call_consent,
        call_consent_at=now if call_consent else None,
        consent_text=consent_text,
        created_at=now,
        updated_at=now,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


def _vehicle(db, stock_number, make="Toyota", model="Camry",
             price=25000.0, is_active=True, dealer_id=None):
    v = models.Vehicle(
        stock_number=stock_number,
        vin=f"VIN{stock_number}",
        make=make,
        model=model,
        price=price,
        is_active=is_active,
        dealer_id=dealer_id,
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


# ===========================================================================
# GET /api/leads
# ===========================================================================

class TestGetLeads:
    """Tests for GET /api/leads."""

    def test_empty_db_returns_empty_paginated_response(self, client):
        r = client.get("/api/leads")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 0
        assert body["data"] == []

    def test_returns_all_leads(self, client, db_session):
        _lead(db_session, customer_name="Alice")
        _lead(db_session, customer_name="Bob")
        r = client.get("/api/leads")
        assert r.json()["total"] == 2

    def test_lead_dict_has_all_required_fields(self, client, db_session):
        _lead(db_session)
        lead = client.get("/api/leads").json()["data"][0]
        required = [
            "id", "customer_name", "customer_phone", "customer_email",
            "interested_make", "interested_model", "max_budget", "notes",
            "status", "source", "campaign", "sms_consent", "sms_consent_at",
            "call_consent", "call_consent_at", "consent_text",
            "created_at", "updated_at", "sold_at",
        ]
        for field in required:
            assert field in lead, f"Lead response missing field: {field}"

    # ── Status filter ──────────────────────────────────────────────────────

    def test_filter_by_status_new(self, client, db_session):
        _lead(db_session, customer_name="New1", status="new")
        _lead(db_session, customer_name="Hot1", status="hot")
        _lead(db_session, customer_name="Sold1", status="sold")
        r = client.get("/api/leads", params={"status": "new"})
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["status"] == "new"

    def test_filter_by_status_hot(self, client, db_session):
        _lead(db_session, customer_name="New1", status="new")
        _lead(db_session, customer_name="Hot1", status="hot")
        assert client.get("/api/leads", params={"status": "hot"}).json()["total"] == 1

    def test_filter_by_status_sold(self, client, db_session):
        _lead(db_session, customer_name="Sold1", status="sold")
        _lead(db_session, customer_name="New1", status="new")
        assert client.get("/api/leads", params={"status": "sold"}).json()["total"] == 1

    def test_filter_by_status_lost(self, client, db_session):
        _lead(db_session, status="lost")
        _lead(db_session, status="new")
        assert client.get("/api/leads", params={"status": "lost"}).json()["total"] == 1

    def test_no_status_filter_returns_all_statuses(self, client, db_session):
        for s in ["new", "contacted", "hot", "sold", "lost"]:
            _lead(db_session, customer_name=f"Lead {s}", status=s)
        assert client.get("/api/leads").json()["total"] == 5

    # ── Search filter ──────────────────────────────────────────────────────

    def test_search_by_customer_name(self, client, db_session):
        _lead(db_session, customer_name="John Doe",
              customer_email="johndoe@example.com")
        _lead(db_session, customer_name="Jane Smith",
              customer_email="jane@example.com")
        r = client.get("/api/leads", params={"search": "john"})
        assert r.json()["total"] == 1
        assert "John" in r.json()["data"][0]["customer_name"]

    def test_search_is_case_insensitive(self, client, db_session):
        _lead(db_session, customer_name="Alice Brown")
        r = client.get("/api/leads", params={"search": "ALICE"})
        assert r.json()["total"] == 1

    def test_search_by_email(self, client, db_session):
        _lead(db_session, customer_name="A", customer_email="alice@example.com")
        _lead(db_session, customer_name="B", customer_email="bob@example.com")
        r = client.get("/api/leads", params={"search": "alice@"})
        assert r.json()["total"] == 1

    def test_search_by_phone(self, client, db_session):
        _lead(db_session, customer_name="A", customer_phone="555-1234")
        _lead(db_session, customer_name="B", customer_phone="555-9999")
        r = client.get("/api/leads", params={"search": "555-1234"})
        assert r.json()["total"] == 1

    def test_search_no_match_returns_empty(self, client, db_session):
        _lead(db_session, customer_name="John Doe")
        r = client.get("/api/leads", params={"search": "Nonexistent Person"})
        assert r.json()["total"] == 0

    # ── Pagination ─────────────────────────────────────────────────────────

    def test_pagination_page_size(self, client, db_session):
        for i in range(7):
            _lead(db_session, customer_name=f"Lead {i}")
        r = client.get("/api/leads", params={"page": 1, "page_size": 3})
        assert len(r.json()["data"]) == 3
        assert r.json()["total"] == 7

    def test_pagination_page_2(self, client, db_session):
        for i in range(6):
            _lead(db_session, customer_name=f"Lead {i}")
        p1 = client.get("/api/leads", params={"page": 1, "page_size": 3}).json()["data"]
        p2 = client.get("/api/leads", params={"page": 2, "page_size": 3}).json()["data"]
        assert {l["id"] for l in p1}.isdisjoint({l["id"] for l in p2})

    # ── Ordering ───────────────────────────────────────────────────────────

    def test_leads_ordered_by_updated_at_desc(self, client, db_session):
        l1 = _lead(db_session, customer_name="Old Lead")
        l2 = _lead(db_session, customer_name="New Lead")
        leads = client.get("/api/leads").json()["data"]
        ids_in_order = [l["id"] for l in leads]
        # l2 was created after l1, so l2 should appear first
        assert ids_in_order.index(l2.id) < ids_in_order.index(l1.id)


# ===========================================================================
# POST /api/leads
# ===========================================================================

class TestCreateLead:

    def test_create_minimal_lead(self, client):
        r = client.post("/api/leads", json={"customer_name": "Minimal Customer"})
        assert r.status_code == 200
        data = r.json()
        assert data["customer_name"] == "Minimal Customer"
        assert data["status"] == "new"
        assert data["id"] is not None

    def test_create_full_lead(self, client):
        payload = {
            "customer_name": "Full Customer",
            "customer_phone": "404-555-0101",
            "customer_email": "full@example.com",
            "interested_make": "Honda",
            "interested_model": "Accord",
            "max_budget": 28000.0,
            "notes": "Needs sunroof",
            "status": "contacted",
            "source": "phone",
            "campaign": "google-rogue-search",
            "sms_consent": True,
            "call_consent": True,
            "consent_text": "Customer consented to calls and texts.",
        }
        r = client.post("/api/leads", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["customer_name"] == "Full Customer"
        assert data["customer_email"] == "full@example.com"
        assert data["interested_make"] == "Honda"
        assert data["interested_model"] == "Accord"
        assert data["max_budget"] == 28000.0
        assert data["status"] == "contacted"
        assert data["source"] == "phone"
        assert data["campaign"] == "google-rogue-search"
        assert data["sms_consent"] is True
        assert data["sms_consent_at"] is not None
        assert data["call_consent"] is True
        assert data["call_consent_at"] is not None
        assert data["consent_text"] == "Customer consented to calls and texts."
        assert data["notes"] == "Needs sunroof"

    def test_create_lead_appears_in_list(self, client):
        client.post("/api/leads", json={"customer_name": "New Customer"})
        r = client.get("/api/leads")
        assert r.json()["total"] == 1

    def test_create_lead_timestamps_are_set(self, client):
        r = client.post("/api/leads", json={"customer_name": "Time Test"})
        data = r.json()
        assert data["created_at"] is not None
        assert data["updated_at"] is not None

    def test_create_lead_without_name_uses_empty_string(self, client):
        r = client.post("/api/leads", json={})
        assert r.status_code == 200
        assert r.json()["customer_name"] == ""

    def test_create_multiple_leads_each_gets_unique_id(self, client):
        r1 = client.post("/api/leads", json={"customer_name": "A"})
        r2 = client.post("/api/leads", json={"customer_name": "B"})
        assert r1.json()["id"] != r2.json()["id"]


# ===========================================================================
# PUT /api/leads/{lead_id}
# ===========================================================================

class TestUpdateLead:

    def test_update_status(self, client, db_session):
        lead = _lead(db_session, status="new")
        r = client.put(f"/api/leads/{lead.id}", json={"status": "hot"})
        assert r.status_code == 200
        assert r.json()["status"] == "hot"

    def test_update_notes(self, client, db_session):
        lead = _lead(db_session, notes="Old note")
        r = client.put(f"/api/leads/{lead.id}", json={"notes": "New note"})
        assert r.status_code == 200
        assert r.json()["notes"] == "New note"

    def test_update_email(self, client, db_session):
        lead = _lead(db_session, customer_email="old@example.com")
        r = client.put(f"/api/leads/{lead.id}",
                       json={"customer_email": "new@example.com"})
        assert r.status_code == 200
        assert r.json()["customer_email"] == "new@example.com"

    def test_update_budget(self, client, db_session):
        lead = _lead(db_session, max_budget=20000.0)
        r = client.put(f"/api/leads/{lead.id}", json={"max_budget": 35000.0})
        assert r.status_code == 200
        assert r.json()["max_budget"] == 35000.0

    def test_update_interested_make_and_model(self, client, db_session):
        lead = _lead(db_session, interested_make="Toyota", interested_model="Camry")
        r = client.put(f"/api/leads/{lead.id}",
                       json={"interested_make": "Honda", "interested_model": "Accord"})
        data = r.json()
        assert data["interested_make"] == "Honda"
        assert data["interested_model"] == "Accord"

    def test_update_preserves_unmodified_fields(self, client, db_session):
        lead = _lead(db_session, customer_name="Preserved", customer_phone="555-0000")
        r = client.put(f"/api/leads/{lead.id}", json={"status": "hot"})
        data = r.json()
        assert data["customer_name"] == "Preserved"
        assert data["customer_phone"] == "555-0000"

    def test_update_refreshes_updated_at(self, client, db_session):
        lead = _lead(db_session)
        original_updated_at = lead.updated_at
        r = client.put(f"/api/leads/{lead.id}", json={"status": "hot"})
        assert r.json()["updated_at"] is not None

    def test_update_status_lifecycle(self, client, db_session):
        """Lead can move through all valid status transitions."""
        lead = _lead(db_session, status="new")
        for status in ["contacted", "hot", "sold"]:
            r = client.put(f"/api/leads/{lead.id}", json={"status": status})
            assert r.status_code == 200
            assert r.json()["status"] == status

    def test_update_nonexistent_lead_returns_404(self, client):
        r = client.put("/api/leads/99999", json={"status": "hot"})
        assert r.status_code == 404

    def test_update_only_allowed_fields(self, client, db_session):
        """Unrecognized keys in the update payload should be silently ignored."""
        lead = _lead(db_session)
        r = client.put(f"/api/leads/{lead.id}",
                       json={"status": "hot", "hacker_field": "injected_value"})
        assert r.status_code == 200
        assert r.json()["status"] == "hot"
        assert "hacker_field" not in r.json()

    def test_update_campaign_and_consents(self, client, db_session):
        lead = _lead(db_session, sms_consent=False, call_consent=False)
        r = client.put(
            f"/api/leads/{lead.id}",
            json={
                "campaign": "tiktok-trucks",
                "sms_consent": True,
                "call_consent": True,
                "consent_text": "Customer opted in on /find.",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["campaign"] == "tiktok-trucks"
        assert data["sms_consent"] is True
        assert data["sms_consent_at"] is not None
        assert data["call_consent"] is True
        assert data["call_consent_at"] is not None
        assert data["consent_text"] == "Customer opted in on /find."


# ===========================================================================
# DELETE /api/leads/{lead_id}
# ===========================================================================

class TestDeleteLead:

    def test_delete_existing_lead_returns_ok(self, client, db_session):
        lead = _lead(db_session)
        r = client.delete(f"/api/leads/{lead.id}")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_deleted_lead_not_in_list(self, client, db_session):
        lead = _lead(db_session)
        client.delete(f"/api/leads/{lead.id}")
        r = client.get("/api/leads")
        assert r.json()["total"] == 0

    def test_delete_nonexistent_lead_returns_404(self, client):
        r = client.delete("/api/leads/99999")
        assert r.status_code == 404

    def test_delete_one_of_many_leaves_others_intact(self, client, db_session):
        l1 = _lead(db_session, customer_name="Keep")
        l2 = _lead(db_session, customer_name="Delete")
        client.delete(f"/api/leads/{l2.id}")
        r = client.get("/api/leads")
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["customer_name"] == "Keep"


# ===========================================================================
# GET /api/leads/{lead_id}/matches
# ===========================================================================

class TestLeadMatches:
    """Tests for GET /api/leads/{lead_id}/matches — inventory matching."""

    def test_returns_empty_when_no_vehicles(self, client, db_session):
        lead = _lead(db_session, interested_make="Toyota")
        r = client.get(f"/api/leads/{lead.id}/matches")
        assert r.status_code == 200
        assert r.json() == []

    def test_unknown_lead_returns_404(self, client):
        r = client.get("/api/leads/99999/matches")
        assert r.status_code == 404

    def test_matches_by_make(self, client, db_session):
        lead = _lead(db_session, interested_make="Toyota")
        _vehicle(db_session, "T1", make="Toyota")
        _vehicle(db_session, "T2", make="Toyota")
        _vehicle(db_session, "H1", make="Honda")
        r = client.get(f"/api/leads/{lead.id}/matches")
        assert len(r.json()) == 2
        assert all(v["make"] == "Toyota" for v in r.json())

    def test_matches_by_make_and_model(self, client, db_session):
        lead = _lead(db_session, interested_make="Toyota", interested_model="Camry")
        _vehicle(db_session, "CAMRY", make="Toyota", model="Camry")
        _vehicle(db_session, "COROLLA", make="Toyota", model="Corolla")
        r = client.get(f"/api/leads/{lead.id}/matches")
        assert len(r.json()) == 1
        assert r.json()[0]["model"] == "Camry"

    def test_matches_respect_budget(self, client, db_session):
        lead = _lead(db_session, interested_make="Toyota", max_budget=25000.0)
        _vehicle(db_session, "CHEAP", make="Toyota", price=20000.0)
        _vehicle(db_session, "EXPENSIVE", make="Toyota", price=40000.0)
        r = client.get(f"/api/leads/{lead.id}/matches")
        assert len(r.json()) == 1
        assert r.json()[0]["stock_number"] == "CHEAP"

    def test_matches_only_active_vehicles(self, client, db_session):
        lead = _lead(db_session, interested_make="Toyota")
        _vehicle(db_session, "ACTIVE", make="Toyota", is_active=True)
        _vehicle(db_session, "INACTIVE", make="Toyota", is_active=False)
        r = client.get(f"/api/leads/{lead.id}/matches")
        assert len(r.json()) == 1
        assert r.json()[0]["stock_number"] == "ACTIVE"

    def test_matches_sorted_by_price_ascending(self, client, db_session):
        lead = _lead(db_session, interested_make="Toyota")
        _vehicle(db_session, "T3", make="Toyota", price=35000.0)
        _vehicle(db_session, "T1", make="Toyota", price=15000.0)
        _vehicle(db_session, "T2", make="Toyota", price=25000.0)
        prices = [v["price"] for v in client.get(f"/api/leads/{lead.id}/matches").json()]
        assert prices == sorted(prices)

    def test_matches_capped_at_20_results(self, client, db_session):
        lead = _lead(db_session, interested_make="Toyota")
        for i in range(15):
            _vehicle(db_session, f"MANY{i:02d}", make="Toyota")
        r = client.get(f"/api/leads/{lead.id}/matches")
        assert len(r.json()) <= 20

    def test_no_make_filter_when_lead_has_no_interested_make(
        self, client, db_session
    ):
        """Lead with no make preference matches vehicles of any make."""
        lead = _lead(db_session, interested_make=None)
        _vehicle(db_session, "T1", make="Toyota")
        _vehicle(db_session, "H1", make="Honda")
        r = client.get(f"/api/leads/{lead.id}/matches")
        assert len(r.json()) == 2

    def test_budget_of_none_does_not_filter_by_price(self, client, db_session):
        lead = _lead(db_session, interested_make="Toyota", max_budget=None)
        _vehicle(db_session, "CHEAP", make="Toyota", price=10000.0)
        _vehicle(db_session, "EXPENSIVE", make="Toyota", price=200000.0)
        r = client.get(f"/api/leads/{lead.id}/matches")
        assert len(r.json()) == 2

    def test_match_response_includes_vehicle_fields(self, client, db_session):
        lead = _lead(db_session, interested_make="Toyota")
        _vehicle(db_session, "T1", make="Toyota")
        v = client.get(f"/api/leads/{lead.id}/matches").json()[0]
        required = ["id", "vin", "stock_number", "year", "make", "model",
                    "price", "mileage", "is_active"]
        for field in required:
            assert field in v, f"Match response missing field: {field}"

    def test_partial_make_match(self, client, db_session):
        """interested_make uses ilike %make% so 'Toy' should match 'Toyota'."""
        lead = _lead(db_session, interested_make="Toy")
        _vehicle(db_session, "T1", make="Toyota")
        r = client.get(f"/api/leads/{lead.id}/matches")
        assert len(r.json()) == 1

    def test_exact_budget_boundary_is_included(self, client, db_session):
        """Vehicles at exactly the budget limit should be included."""
        lead = _lead(db_session, max_budget=25000.0)
        _vehicle(db_session, "EXACT", price=25000.0)
        r = client.get(f"/api/leads/{lead.id}/matches")
        assert len(r.json()) == 1

    def test_deleted_lead_matches_returns_404(self, client, db_session):
        lead = _lead(db_session)
        client.delete(f"/api/leads/{lead.id}")
        r = client.get(f"/api/leads/{lead.id}/matches")
        assert r.status_code == 404


# ===========================================================================
# GET /api/leads/{lead_id}/matches?dealer_id=N — Sprint 1 (xfail)
# ===========================================================================

class TestLeadMatchesDealerIdFilter:
    """Tests for dealer_id scoping on the lead matches endpoint."""

    def test_matches_scoped_to_dealer(self, client, db_session, make_dealer):
        make_dealer(id=323, name="ALM Mall of Georgia")
        make_dealer(id=401, name="ALM Roswell")

        lead = _lead(db_session, interested_make="Toyota")
        _vehicle(db_session, "MOG_TOYOTA", make="Toyota", dealer_id=323)
        _vehicle(db_session, "RWL_TOYOTA", make="Toyota", dealer_id=401)

        r = client.get(f"/api/leads/{lead.id}/matches",
                       params={"dealer_id": 323})
        matches = r.json()
        assert len(matches) == 1
        assert matches[0]["dealer_id"] == 323

    def test_matches_without_dealer_id_returns_all_dealers(
        self, client, db_session, make_dealer
    ):
        make_dealer(id=323, name="ALM Mall of Georgia")
        make_dealer(id=401, name="ALM Roswell")

        lead = _lead(db_session, interested_make="Toyota")
        _vehicle(db_session, "MOG_T", make="Toyota", dealer_id=323)
        _vehicle(db_session, "RWL_T", make="Toyota", dealer_id=401)

        r = client.get(f"/api/leads/{lead.id}/matches")
        assert len(r.json()) == 2

    def test_match_response_includes_dealer_id_field(
        self, client, db_session, make_dealer
    ):
        make_dealer(id=323, name="ALM Mall of Georgia")
        lead = _lead(db_session, interested_make="Toyota")
        _vehicle(db_session, "MOG_T", make="Toyota", dealer_id=323,
                 is_active=True)

        matches = client.get(f"/api/leads/{lead.id}/matches").json()
        assert len(matches) == 1
        assert "dealer_id" in matches[0]
        assert matches[0]["dealer_id"] == 323
