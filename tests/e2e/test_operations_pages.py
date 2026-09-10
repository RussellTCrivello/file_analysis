"""Frontend pages render for authenticated users (Operations UI)."""


def test_operations_pages_render(app, admin_client):
    for url, marker in (
        ("/operations/input", "Start Analysis"),
        ("/operations/import", "Import Center"),
        ("/operations/jobs", "Jobs"),
    ):
        resp = admin_client.get(url)
        assert resp.status_code == 200, url
        assert marker.encode() in resp.data, url

    # job detail page renders for any id (loads data via API)
    resp = admin_client.get("/operations/jobs/XYZ123")
    assert resp.status_code == 200


def test_dashboard_has_operations_widget(app, admin_client):
    resp = admin_client.get("/")
    assert resp.status_code == 200
    assert b"operations" in resp.data.lower() or b"Operations" in resp.data
