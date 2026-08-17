from sqlalchemy import select

from app.db import session as db_session
from app.models.eval_models import EvalCase, EvalRun, EvalRunItem


def _auth_headers(client) -> dict[str, str]:
    payload = {
        "username": "evaluser",
        "email": "eval@example.com",
        "password": "secret123",
    }
    client.post("/api/auth/register", json=payload)
    login = client.post(
        "/api/auth/login",
        json={"username": "evaluser", "password": "secret123"},
    )
    token = login.json()["data"]["token"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _fake_ask_knowledge_base(**kwargs):
    return {
        "ok": True,
        "status": "success",
        "original_query": kwargs.get("query"),
        "optimized_query": f"优化:{kwargs.get('query')}",
        "rewrite_fallback": False,
        "hits": [
            {
                "title": "友情",
                "source_path": "docs/友情.md",
                "content": "友情胜过一般的爱情",
                "score": 0.9,
            }
        ],
        "answer": "【回答】\n友情很重要。\n\n【依据材料】\n[1] docs/友情.md",
        "error_stage": None,
        "error_message": None,
        "duration_ms": 12,
        "model": "fake-model",
    }


async def _fake_judge_ask_result(*_args, **_kwargs):
    return {
        "score": 88,
        "reason": "命中期望文档且覆盖要点",
        "retrieval_ok": True,
        "needs_review": False,
        "passed": True,
    }


def test_eval_case_crud_and_run_flow(client, monkeypatch):
    monkeypatch.setattr("app.services.evals.ask_knowledge_base", _fake_ask_knowledge_base)
    monkeypatch.setattr("app.services.evals.judge_ask_result", _fake_judge_ask_result)
    monkeypatch.setattr(
        "app.services.evals.get_llm_client",
        lambda: type("C", (), {"model": "fake-model"})(),
    )

    headers = _auth_headers(client)

    created = client.post(
        "/api/evals/cases",
        headers=headers,
        json={
            "query": "什么是友情",
            "expected_doc": "docs/友情.md",
            "expected_points": "友情胜过爱情",
        },
    )
    assert created.status_code == 200
    case_id = created.json()["data"]["id"]

    listed = client.get("/api/evals/cases", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] >= 1

    updated = client.patch(
        f"/api/evals/cases/{case_id}",
        headers=headers,
        json={"expected_points": "友情很重要"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["expected_points"] == "友情很重要"

    run_resp = client.post(
        "/api/evals/runs",
        headers=headers,
        json={"name": "第一场", "case_ids": [case_id]},
    )
    assert run_resp.status_code == 200
    run = run_resp.json()["data"]
    assert run["status"] == "pending"
    assert run["total"] == 1
    assert len(run["items"]) == 1
    assert run["items"][0]["query_snapshot"] == "什么是友情"
    assert run["items"][0]["expected_points_snapshot"] == "友情很重要"
    run_id = run["id"]
    item_id = run["items"][0]["id"]

    # 改题库不影响已建任务快照
    client.patch(
        f"/api/evals/cases/{case_id}",
        headers=headers,
        json={"query": "改掉的问题"},
    )
    detail = client.get(f"/api/evals/runs/{run_id}", headers=headers)
    assert detail.json()["data"]["items"][0]["query_snapshot"] == "什么是友情"

    started = client.post(f"/api/evals/runs/{run_id}/start", headers=headers)
    assert started.status_code == 200
    body = started.json()["data"]
    assert body["status"] == "done"
    assert body["model"] == "fake-model"
    assert body["items"][0]["ask_status"] == "success"
    assert body["items"][0]["optimized_query"] == "优化:什么是友情"
    assert "友情很重要" in (body["items"][0]["answer"] or "")
    assert body["items"][0]["hits_json"] and "docs/友情.md" in body["items"][0]["hits_json"]
    assert body["items"][0]["duration_ms"] == 12
    assert body["items"][0]["auto_score"] == 88
    assert body["items"][0]["final_score"] == 88
    assert body["items"][0]["passed"] is True
    assert body["items"][0]["auto_reason"] == "命中期望文档且覆盖要点"

    scored = client.patch(
        f"/api/evals/runs/{run_id}/items/{item_id}/score",
        headers=headers,
        json={"human_score": 80, "human_comment": "还行"},
    )
    assert scored.status_code == 200
    assert scored.json()["data"]["final_score"] == 80

    deleted_run = client.delete(f"/api/evals/runs/{run_id}", headers=headers)
    assert deleted_run.status_code == 200

    deleted_case = client.delete(f"/api/evals/cases/{case_id}", headers=headers)
    assert deleted_case.status_code == 200

    db = db_session.SessionLocal()
    try:
        assert db.get(EvalCase, case_id) is None
        assert db.execute(select(EvalRun).where(EvalRun.id == run_id)).scalar_one_or_none() is None
        assert (
            db.execute(select(EvalRunItem).where(EvalRunItem.run_id == run_id)).scalars().first()
            is None
        )
    finally:
        db.close()
