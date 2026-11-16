from app.verify_campaign import audit_campaign


def fixture():
    campaign = {
        "name": "test_pokotilo_campaign1", "state": "active", "group_id": 9799,
        "traffic_source_id": 836, "domain_id": 1813,
    }
    streams = [
        {"type": "regular", "schema": "redirect", "state": "active",
         "action_type": "http", "action_payload": "https://www.google.com/",
         "filters": [{"name": "country", "mode": "accept", "payload": ["DE"]}]},
        {"type": "default", "schema": "landings", "state": "active", "filters": [],
         "landings": [], "offers": [{"offer_id": 13972, "share": 50, "state": "active"},
                                  {"offer_id": 11733, "share": 50, "state": "active"}]},
    ]
    return campaign, streams


def audit(campaign, streams):
    return audit_campaign(campaign, streams, name="test_pokotilo_campaign1", country="DE",
                          group_id=9799, source_id=836, domain_id=1813,
                          offer_ids=[13972, 11733])


def test_valid_configuration():
    assert audit(*fixture()) == ([], [])


def test_wrong_country_and_source_caught():
    campaign, streams = fixture()
    campaign["traffic_source_id"] = 7
    streams[0]["filters"][0]["payload"] = ["FR"]
    issues, _ = audit(campaign, streams)
    assert len(issues) == 2


def test_missing_domain_reported_as_unverified():
    campaign, streams = fixture()
    del campaign["domain_id"]
    issues, warnings = audit(campaign, streams)
    assert not issues and len(warnings) == 1


def test_invalid_offers_or_stream_count():
    campaign, streams = fixture()
    streams[1]["offers"][0]["share"] = 60
    issues, _ = audit(campaign, streams)
    assert any("100%" in issue for issue in issues)
    issues, _ = audit(campaign, streams[:1])
    assert any("ровно два" in issue for issue in issues)


def test_string_encoded_country_filter_is_supported():
    campaign, streams = fixture()
    streams[0]["filters"][0]["payload"] = '["DE"]'
    assert audit(campaign, streams) == ([], [])
