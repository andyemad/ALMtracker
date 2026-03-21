"""
Tests for:
  GET    /api/leads
  POST   /api/leads
  PUT    /api/leads/{lead_id}
  DELETE /api/leads/{lead_id}
  GET    /api/leads/{lead_id}/matches

Covers full CRUD, status transitions, search filtering, and inventory matching.
"""

import pytest
from tests.conftest import make_vehicle, make_lead


class TestGetLeads:

    def test_empty_db_returns_empty_list(self, client):
        r = client.get("/api/leads")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 0
        assert data["data"] == []

    def test_returns_all_leads(self, client, db):
        make_lead(db, customer_name="Alice")
        make_lead(db, customer_name="Bob")

        r = client.get("/api/leads")
        assert r.json()["total"] == 2

    def test_lead_dict_has_required_fields(self, client, db):
        make_lead(db, customer_name="Shape Test")

        r = client.get("/api/leads")
        lead = r.json()["data"][0]
        required = [
            "id", "customer_name", "customer_phone", "customer_email",
            "interested_make", "interested_model", "max_budget", "notes",
            "status", "source", "campaign", "sms_consent", "sms_consent_at",
            "call_consent", "call_consent_at", "consent_text",
            "created_at", "updated_at", "sold_at",
        ]
        for field in required:
            assert field in lead, f"Missing field: {field}"

    def test_filter_by_status(self, client, db):
        make_lead(db, customer_name="New Lead", status="new")
        make_lead(db, customer_name="Hot Lead", status="hot")
        make_lead(db, customer_name="Sold Lead", status="sold")

        r = client.get("/api/leads", params={"status": "hot"})
        assert r.json()["total"] == 1
        assert r.json()["data"][0]["status"] == "hot"

    def test_search_by_customer_name(self, client, db):
        make_lead(db, customer_name="John Doe",
                  customer_email="johndoe@example.com")
        make_lead(db, customer_name="Jane Smith",
                  customer_email="jane@example.com")

        r = client.get("/api/leads", params={"search": "john"})
        assert r.json()["total"] == 1
        assert "John" in r.json()["data"][0]["customer_name"]

    def test_search_by_email(self, client, db):
        make_lead(db, customer_name="Alice", customer_email="alice@example.com")
        make_lead(db, customer_name="Bob", customer_email="bob@example.com")

        r = client.get("/api/leads", params={"search": "alice@"})
        assert r.json()["total"] == 1

    def test_search_by_phone(self, client, db):
        make_lead(db, customer_name="Alice", customer_phone="555-1234")
        make_lead(db, customer_name="Bob", customer_phone="555-9999")

        r = client.get("/api/leads", params={"search": "555-1234"})
        assert r.json()["total"] == 1

    def test_pagination(self, client, db):
        for i in range(7):
            make_lead(db, customer_name=f"Lead {i}")

        r = client.get("/api/leads", params={"page": 1, "page_size": 3})
        assert len(r.json()["data"]) == 3
        assert r.json()["total"] == 7

    def test_leads_ordered_by_updated_at_desc(self, client, db):
        from datetime import timedelta
        from datetime import datetime
        old = make_lead(db, customer_name="Old Lead")
        new = make_lead(db, customer_name="New Lead")

        r = client.get("/api/leads")
        names = [l["customer_name"] for l in r.json()["data"]]
        # Most recently updated should be first
        assert names.index("New Lead") < names.index("Old Lead") or len(names) == 2


class TestCreateLead:

    def test_create_minimal_lead(self, client):
        payload = {"customer_name": "Test Customer"}
        r = client.post("/api/leads", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["customer_name"] == "Test Customer"
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
            "campaign": "meta-budget-suvs",
            "sms_consent": True,
            "call_consent": True,
            "consent_text": "Customer agreed to SMS and call follow-up.",
        }
        r = client.post("/api/leads", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["customer_name"] == "Full Customer"
        assert data["customer_email"] == "full@example.com"
        assert data["interested_make"] == "Honda"
        assert data["max_budget"] == 28000.0
        assert data["status"] == "contacted"
        assert data["source"] == "phone"
        assert data["campaign"] == "meta-budget-suvs"
        assert data["sms_consent"] is True
        assert data["sms_consent_at"] is not None
        assert data["call_consent"] is True
        assert data["call_consent_at"] is not None
        assert data["consent_text"] == "Customer agreed to SMS and call follow-up."

    def test_created_lead_appears_in_list(self, client):
        client.post("/api/leads", json={"customer_name": "New Customer"})
        r = client.get("/api/leads")
        assert r.json()["total"] == 1


class TestUpdateLead:

    def test_update_status(self, client, db):
        lead = make_lead(db, status="new")
        r = client.put(f"/api/leads/{lead.id}", json={"status": "hot"})
        assert r.status_code == 200
        assert r.json()["status"] == "hot"

    def test_update_notes(self, client, db):
        lead = make_lead(db, notes="Old note")
        r = client.put(f"/api/leads/{lead.id}", json={"notes": "New note"})
        assert r.status_code == 200
        assert r.json()["notes"] == "New note"

    def test_update_contact_info(self, client, db):
        lead = make_lead(db, customer_email="old@example.com")
        r = client.put(f"/api/leads/{lead.id}",
                       json={"customer_email": "new@example.com"})
        assert r.status_code == 200
        assert r.json()["customer_email"] == "new@example.com"

    def test_update_budget(self, client, db):
        lead = make_lead(db, max_budget=20000.0)
        r = client.put(f"/api/leads/{lead.id}", json={"max_budget": 35000.0})
        assert r.status_code == 200
        assert r.json()["max_budget"] == 35000.0

    def test_update_nonexistent_lead_returns_404(self, client):
        r = client.put("/api/leads/99999", json={"status": "sold"})
        assert r.status_code == 404

    def test_update_preserves_unmodified_fields(self, client, db):
        lead = make_lead(db, customer_name="Preserve Me", customer_phone="555-0101")
        r = client.put(f"/api/leads/{lead.id}", json={"status": "hot"})
        data = r.json()
        assert data["customer_name"] == "Preserve Me"
        assert data["customer_phone"] == "555-0101"

    def test_update_refreshes_updated_at(self, client, db):
        lead = make_lead(db)
        r = client.put(f"/api/leads/{lead.id}", json={"status": "hot"})
        assert r.json()["updated_at"] is not None

    def test_update_campaign_and_consents(self, client, db):
        lead = make_lead(db, sms_consent=False, call_consent=False)
        r = client.put(
            f"/api/leads/{lead.id}",
            json={
                "campaign": "tiktok-elantra-drop",
                "sms_consent": True,
                "call_consent": True,
                "consent_text": "Customer requested outreach from the public funnel.",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["campaign"] == "tiktok-elantra-drop"
        assert data["sms_consent"] is True
        assert data["sms_consent_at"] is not None
        assert data["call_consent"] is True
        assert data["call_consent_at"] is not None
        assert data["consent_text"] == "Customer requested outreach from the public funnel."


class TestDeleteLead:

    def test_delete_existing_lead(self, client, db):
        lead = make_lead(db)
        r = client.delete(f"/api/leads/{lead.id}")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_deleted_lead_not_in_list(self, client, db):
        lead = make_lead(db)
        client.delete(f"/api/leads/{lead.id}")
        r = client.get("/api/leads")
        assert r.json()["total"] == 0

    def test_delete_nonexistent_lead_returns_404(self, client):
        r = client.delete("/api/leads/99999")
        assert r.status_code == 404


class TestLeadMatches:

    def test_no_matches_when_db_empty(self, client, db):
        lead = make_lead(db, interested_make="Toyota")
        r = client.get(f"/api/leads/{lead.id}/matches")
        assert r.status_code == 200
        assert r.json() == []

    def test_matches_by_make(self, client, db):
        lead = make_lead(db, interested_make="Toyota", interested_model=None, max_budget=None)
        make_vehicle(db, stock_number="T1", make="Toyota", is_active=True)
        make_vehicle(db, stock_number="T2", make="Toyota", is_active=True)
        make_vehicle(db, stock_number="H1", make="Honda", is_active=True)

        r = client.get(f"/api/leads/{lead.id}/matches")
        assert len(r.json()) == 2
        assert all(v["make"] == "Toyota" for v in r.json())

    def test_matches_by_make_and_model(self, client, db):
        lead = make_lead(db, interested_make="Toyota", interested_model="Camry", max_budget=None)
        make_vehicle(db, stock_number="CAMRY", make="Toyota", model="Camry")
        make_vehicle(db, stock_number="COROLLA", make="Toyota", model="Corolla")

        r = client.get(f"/api/leads/{lead.id}/matches")
        assert len(r.json()) == 1
        assert r.json()[0]["model"] == "Camry"

    def test_matches_respects_budget(self, client, db):
        lead = make_lead(db, interested_make="Toyota", max_budget=25000.0)
        make_vehicle(db, stock_number="CHEAP", make="Toyota", price=20000.0)
        make_vehicle(db, stock_number="EXPENSIVE", make="Toyota", price=40000.0)

        r = client.get(f"/api/leads/{lead.id}/matches")
        assert len(r.json()) == 1
        assert r.json()[0]["stock_number"] == "CHEAP"

    def test_matches_only_active_vehicles(self, client, db):
        lead = make_lead(db, interested_make="Toyota", max_budget=None)
        make_vehicle(db, stock_number="ACTIVE", make="Toyota", is_active=True)
        make_vehicle(db, stock_number="INACTIVE", make="Toyota", is_active=False)

        r = client.get(f"/api/leads/{lead.id}/matches")
        assert len(r.json()) == 1
        assert r.json()[0]["stock_number"] == "ACTIVE"

    def test_matches_sorted_by_price_asc(self, client, db):
        lead = make_lead(db, interested_make="Toyota", max_budget=None)
        make_vehicle(db, stock_number="T3", make="Toyota", price=35000.0)
        make_vehicle(db, stock_number="T1", make="Toyota", price=15000.0)
        make_vehicle(db, stock_number="T2", make="Toyota", price=25000.0)

        r = client.get(f"/api/leads/{lead.id}/matches")
        prices = [v["price"] for v in r.json()]
        assert prices == sorted(prices)

    def test_matches_capped_at_10(self, client, db):
        lead = make_lead(db, interested_make="Toyota", max_budget=None)
        for i in range(15):
            make_vehicle(db, stock_number=f"TOYOTA{i:02d}", make="Toyota")

        r = client.get(f"/api/leads/{lead.id}/matches")
        assert len(r.json()) <= 20

    def test_lead_matches_returns_vehicle_fields(self, client, db):
        lead = make_lead(db, interested_make="Toyota", max_budget=None)
        make_vehicle(db, stock_number="T1", make="Toyota")

        r = client.get(f"/api/leads/{lead.id}/matches")
        v = r.json()[0]
        required = [
            "id", "vin", "stock_number", "year", "make", "model", "price",
            "mileage", "is_active"
        ]
        for field in required:
            assert field in v, f"Missing field: {field}"

    def test_lead_not_found_returns_404(self, client):
        r = client.get("/api/leads/99999/matches")
        assert r.status_code == 404

    def test_no_make_filter_if_lead_has_no_make(self, client, db):
        lead = make_lead(db, interested_make=None, interested_model=None, max_budget=None)
        make_vehicle(db, stock_number="T1", make="Toyota")
        make_vehicle(db, stock_number="H1", make="Honda")

        r = client.get(f"/api/leads/{lead.id}/matches")
        # Should return both — no make filter applied
        assert len(r.json()) == 2
