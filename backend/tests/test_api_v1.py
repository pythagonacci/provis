from fastapi.testclient import TestClient
from app.main import app


client = TestClient(app)


def test_v1_overview_and_caps(monkeypatch, tmp_path):
    # Prepare fake repo dir and status
    from app.config import settings
    from app.status import StatusStore
    repo_id = "repo_test_v1"
    base = tmp_path / repo_id
    (base / "capabilities").mkdir(parents=True, exist_ok=True)

    # Minimal artifacts
    (base / "tree.json").write_text("{}")
    (base / "files.json").write_text('{"files": []}')
    (base / "metrics.json").write_text('{"filesCount": 0}')
    (base / "capabilities.json").write_text('{"capabilities": []}')
    (base / "capabilities" / "cap_root").mkdir(parents=True, exist_ok=True)
    (base / "capabilities" / "cap_root" / "capability.json").write_text('{"id":"cap_root","name":"/"}')
    (base / "capabilities" / "index.json").write_text('{"index": [{"id":"cap_root","name":"/"}]}')

    # Point DATA_DIR to tmp
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))

    # Write status done
    store = StatusStore(base)
    store.update(jobId="job_v1", repoId=repo_id, phase="done", pct=100, filesParsed=0, imports=0, warnings=[])

    # Overview
    r = client.get(f"/v1/repo/{repo_id}")
    assert r.status_code == 200, r.text
    j = r.json()
    assert "tree" in j and "files" in j and "capabilities" in j and "metrics" in j

    # List caps
    r2 = client.get(f"/v1/repo/{repo_id}/capabilities")
    assert r2.status_code == 200
    assert isinstance(r2.json(), list)

    # Get one cap
    r3 = client.get(f"/v1/repo/{repo_id}/capabilities/cap_root")
    assert r3.status_code == 200
    cj = r3.json()
    assert cj.get("id") == "cap_root"

    # Suggestions
    r4 = client.get(f"/v1/repo/{repo_id}/suggestions")
    assert r4.status_code == 200
    sj = r4.json()
    assert isinstance(sj.get("suggestions"), list)

