import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///" + tempfile.mktemp(suffix=".db")
os.environ["DEMO_MODE"] = "true"
os.environ["APP_PASSWORD"] = "test-password"
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine
from app.shares import redistribute
import pytest


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app, headers={"X-Requested-With": "KeitaroWrapper"}) as c:
        c.auth = ("admin", "test-password")
        yield c


def create(c):
    data = {
        "name": "demo",
        "country": "DE",
        "offer_id": 1,
        "domain_id": 1,
        "group_id": 1,
        "traffic_source_id": 1,
        "request_id": str(uuid4()),
    }
    r = c.post("/api/campaigns", json=data)
    assert r.status_code == 200, r.text
    return r.json(), data


def test_create_and_idempotency(client):
    campaign, data = create(client)
    assert client.post("/api/campaigns", json=data).json()["id"] == campaign["id"]
    streams = client.get(f"/api/campaigns/{campaign['id']}/streams").json()
    assert len(streams) == 2
    assert streams[0]["filters"][0]["payload"] == ["DE"]
    assert streams[0]["action_payload"] == "https://www.google.com/"
    assert streams[1]["offers"][0]["share"] == 100
    assert campaign["state"] == "active"


def test_draft_push_and_conflict(client):
    campaign, _ = create(client)
    cid = campaign["id"]
    sid = client.get(f"/api/campaigns/{cid}/streams").json()[1]["id"]
    d = client.post(f"/api/campaigns/{cid}/streams/{sid}/fetch", json={}).json()
    d["offers"].append({"offer_id": 2, "share": 0, "state": "active", "locked": False})
    response = client.put(
        f"/api/drafts/{sid}", json={"revision": d["revision"], "offers": d["offers"]}
    )
    assert response.status_code == 200, response.text
    assert [x["share"] for x in response.json()["offers"]] == [50, 50]
    assert (
        client.post(f"/api/drafts/{sid}/push", json={"revision": 1}).status_code == 409
    )
    assert (
        client.post(f"/api/drafts/{sid}/push", json={"revision": 2}).status_code == 200
    )


def test_validation_and_auth(client):
    assert client.get("/api/campaigns", auth=("bad", "bad")).status_code == 401
    assert (
        client.post(
            "/api/campaigns", json={}, headers={"X-Requested-With": ""}
        ).status_code
        == 403
    )
    assert client.post("/api/campaigns", json={"country": "ZZ"}).status_code == 422


def test_shares():
    rows = redistribute(
        [{"offer_id": i, "share": 0, "state": "active"} for i in range(3)]
    )
    assert [x["share"] for x in rows] == [33, 33, 34]
    rows[0].update(share=40, locked=True)
    assert [x["share"] for x in redistribute(rows)] == [40, 30, 30]
    with pytest.raises(ValueError):
        redistribute([{"offer_id": 1, "share": 0, "state": "disabled"}])


def test_external_change_conflict(client):
    from app.keitaro import api

    campaign, _ = create(client)
    cid = campaign["id"]
    sid = client.get(f"/api/campaigns/{cid}/streams").json()[1]["id"]
    client.post(f"/api/campaigns/{cid}/streams/{sid}/fetch", json={})
    next(s for s in api.data["streams"] if s["id"] == sid)["name"] = "changed outside"
    assert (
        client.post(f"/api/drafts/{sid}/push", json={"revision": 1}).status_code == 409
    )


def test_partial_creation_stays_disabled(client, monkeypatch):
    from app.keitaro import api, UpstreamError

    original = api.request

    async def fail(method, path, payload=None):
        if method == "POST" and path == "streams":
            raise UpstreamError(500, "Injected")
        return await original(method, path, payload)

    monkeypatch.setattr(api, "request", fail)
    data = {
        "name": "partial",
        "country": "DE",
        "offer_id": 1,
        "domain_id": 1,
        "group_id": 1,
        "traffic_source_id": 1,
        "request_id": str(uuid4()),
    }
    assert client.post("/api/campaigns", json=data).status_code == 502
    assert api.data["campaigns"][-1]["state"] == "disabled"
    assert client.post("/api/campaigns", json=data).status_code == 409


def test_cannot_edit_foreign_campaign(client):
    from app.keitaro import api

    api.data["campaigns"].append({"id": 98765, "name": "production"})
    assert client.get("/api/campaigns/98765/streams").status_code == 403


def test_catalogs_report_missing_dependencies(client, monkeypatch):
    from app.keitaro import api

    monkeypatch.setitem(api.data, "domains", [])
    monkeypatch.setitem(api.data, "traffic_sources", [])
    result = client.get("/api/catalogs").json()
    assert result["missing"] == ["domains", "sources"]
    assert result["groups"]


def test_base_domain_requires_explicit_selection(client):
    _, data = create(client)
    data.update(request_id=str(uuid4()), domain_id=None, use_base_domain=True)
    response = client.post('/api/campaigns', json=data)
    assert response.status_code == 200, response.text
    assert 'domain_id' not in response.json()
    data.update(request_id=str(uuid4()), use_base_domain=False)
    assert client.post('/api/campaigns', json=data).status_code == 422


def test_catalog_failure_does_not_hide_other_catalogs(client, monkeypatch):
    from app.keitaro import api, UpstreamError
    original = api.request
    async def request(method, path, payload=None):
        if path == 'traffic_sources':
            raise UpstreamError(403, 'Forbidden')
        return await original(method, path, payload)
    monkeypatch.setattr(api, 'request', request)
    response = client.get('/api/catalogs')
    assert response.status_code == 200
    assert response.json()['offers']
    assert response.json()['errors']['sources']['status'] == 403


def test_deleted_offer_rejected_before_creation(client, monkeypatch):
    from app.keitaro import api
    monkeypatch.setitem(api.data, 'offers', [{'id': 1, 'state': 'deleted'}])
    before = len(api.data['campaigns'])
    data = dict(name='deleted', country='DE', offer_id=1, domain_id=1,
                group_id=1, traffic_source_id=1, request_id=str(uuid4()))
    assert client.post('/api/campaigns', json=data).status_code == 422
    assert len(api.data['campaigns']) == before


def test_ignored_redirect_never_enables_campaign(client, monkeypatch):
    from app.keitaro import api
    original = api.request
    async def request(method, path, payload=None):
        if method == 'POST' and path == 'streams' and payload.get('schema') == 'redirect':
            payload = {**payload, 'action_payload': ''}
        return await original(method, path, payload)
    monkeypatch.setattr(api, 'request', request)
    data = dict(name='invalid_redirect', country='DE', offer_id=1, domain_id=1,
                group_id=1, traffic_source_id=1, request_id=str(uuid4()))
    response = client.post('/api/campaigns', json=data)
    assert response.status_code == 502
    assert api.data['campaigns'][-1]['state'] == 'disabled'


def test_volatile_timestamp_does_not_block_draft(client):
    from app.keitaro import api
    campaign, _ = create(client)
    cid = campaign['id']
    sid = client.get(f'/api/campaigns/{cid}/streams').json()[1]['id']
    client.post(f'/api/campaigns/{cid}/streams/{sid}/fetch', json={})
    next(s for s in api.data['streams'] if s['id'] == sid)['updated_at'] = 'later'
    assert client.post(f'/api/drafts/{sid}/push', json={'revision': 1}).status_code == 200


def test_removed_offer_archived_locally_and_pin_survives_push(client):
    from app.keitaro import api
    campaign, _ = create(client)
    cid = campaign['id']
    sid = client.get(f'/api/campaigns/{cid}/streams').json()[1]['id']
    path = f'/api/campaigns/{cid}/streams/{sid}/fetch'
    d = client.post(path, json={}).json()
    rows = [{'offer_id': 1, 'share': 40, 'state': 'active', 'locked': True},
            {'offer_id': 2, 'share': 60, 'state': 'active'},
            {'offer_id': 3, 'share': 0, 'state': 'disabled'}]
    d = client.put(f'/api/drafts/{sid}', json={'revision': d['revision'], 'offers': rows}).json()
    assert d['dirty'] is True
    assert client.post(f'/api/drafts/{sid}/push', json={'revision': d['revision']}).status_code == 200
    remote = next(s for s in api.data['streams'] if s['id'] == sid)
    assert [o['offer_id'] for o in remote['offers']] == [1, 2]
    d = client.post(path, json={}).json()
    assert d['dirty'] is False
    assert d['offers'][0]['locked'] is True
    assert d['offers'][2]['state'] == 'disabled'
    remote['offers'] = [remote['offers'][0]]
    remote['offers'][0]['share'] = 100
    d = client.post(path, json={}).json()
    assert next(o for o in d['offers'] if o['offer_id'] == 2)['state'] == 'disabled'
    assert d['dirty'] is False


def test_cancel_removes_unpublished_additions_and_keeps_archive(client):
    campaign, _ = create(client)
    cid = campaign['id']
    sid = client.get(f'/api/campaigns/{cid}/streams').json()[1]['id']
    path = f'/api/campaigns/{cid}/streams/{sid}/fetch'
    d = client.post(path, json={}).json()
    d = client.put(f'/api/drafts/{sid}', json={'revision': d['revision'], 'offers': d['offers'] + [
        {'offer_id': 2, 'share': 0, 'state': 'active'}]}).json()
    client.post(f'/api/drafts/{sid}/cancel', json={'revision': d['revision']})
    d = client.post(path, json={}).json()
    assert [o['offer_id'] for o in d['offers']] == [1]
    assert d['dirty'] is False


def test_restore_archived_offer_and_cancel_preserve_committed_state(client):
    campaign, _ = create(client)
    cid = campaign['id']
    sid = client.get(f'/api/campaigns/{cid}/streams').json()[1]['id']
    path = f'/api/campaigns/{cid}/streams/{sid}/fetch'
    def edit_and_push(rows):
        d = client.post(path, json={}).json()
        d = client.put(f'/api/drafts/{sid}', json={'revision': d['revision'], 'offers': rows}).json()
        r = client.post(f'/api/drafts/{sid}/push', json={'revision': d['revision']})
        assert r.status_code == 200, r.text
        return r.json()
    rows = [{'offer_id': 1, 'share': 0, 'state': 'active'},
            {'offer_id': 2, 'share': 0, 'state': 'active'}]
    edit_and_push(rows)
    rows[1]['state'] = 'disabled'
    assert len(edit_and_push(rows)['offers']) == 1
    rows[1]['state'] = 'active'
    result = edit_and_push(rows)
    assert [x['share'] for x in result['offers']] == [50, 50]
    d = client.post(path, json={}).json()
    changed = [dict(x) for x in d['offers']]
    changed[0]['state'] = 'disabled'
    d = client.put(f'/api/drafts/{sid}', json={'revision': d['revision'], 'offers': changed}).json()
    client.post(f'/api/drafts/{sid}/cancel', json={'revision': d['revision']})
    d = client.post(path, json={}).json()
    assert [x['share'] for x in d['offers']] == [50, 50]
    assert not d['dirty']
