"""S5 shadow evaluation matrix with synthetic fixtures.

Drives the real S4 adapter -> S1 spool -> S2 consumer chain end to end with
fixture transcripts and scripted runners. Nothing here registers a hook,
calls a model, or touches ``~/.claude``/``~/.codex``/USMC live data.

Optional S3 bridge: if ``usmc.lesson_contract`` is importable (S3 branch on
PYTHONPATH), staged lesson candidates are ingested into a temporary USMC DB.

Set ``WFL_S5_REPORT=<path>`` to write the collected metrics as JSON.
"""

from __future__ import annotations

import io
import json
import os
import threading
from pathlib import Path

import pytest

from workflowhooker.candidates import BudgetSpec, CandidateSpool, LifecycleController
from workflowhooker.cli import main
from workflowhooker.extractor_consumer import REQUIRED_SKILLS, ExtractorConsumer
from workflowhooker.providers.shadow import (
    ProviderPayloadError,
    dispatch_shadow_lifecycle,
)

EXTRACTOR_VERSION = "workflow-extract@1.1.0+skill-extractor@1.0.0"
METRICS: dict[str, dict] = {}

SECRETS = {
    "openai_key": "sk-proj-AbCdEf0123456789XyZ",
    "github_pat": "ghp_0123456789abcdefABCDEF",
    "bearer": "Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig",
    "assigned_password": "password=Hunter2Hunter2",
    "email": "fixture@example.org",
    "phone": "+49 170 1234567",
    "ipv4": "192.0.2.10",
    "windows_user": "C:\\Users\\ExampleUser\\secret.txt",
    "aws_key_id": "AKIAABCDEFGHIJKLMNOP",
    # Formats outside the documented secret-pii-v1 pattern set:
    "german_passwort": "Passwort: Sommer2026!",
    "slack_token": "xoxb-1234567890-abcdefghijkl",
    "pem_private_key": "-----BEGIN PRIVATE KEY-----MIIEvQIBADANBg",
    "url_credentials": "https://admin:TopSecret99@intranet.local/x",
    "iban": "DE89370400440532013000",
    "jwt_unlabelled": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl",
}
# Only the raw secret tail is checked (the label may legitimately remain).
SECRET_PROBES = {
    "openai_key": "AbCdEf0123456789XyZ",
    "github_pat": "0123456789abcdefABCDEF",
    "bearer": "payload.sig",
    "assigned_password": "Hunter2Hunter2",
    "email": "fixture@example.org",
    "phone": "170 1234567",
    "ipv4": "192.0.2.10",
    "windows_user": "ExampleUser",
    "aws_key_id": "AKIAABCDEFGHIJKLMNOP",
    "german_passwort": "Sommer2026!",
    "slack_token": "abcdefghijkl",
    "pem_private_key": "MIIEvQIBADANBg",
    "url_credentials": "TopSecret99",
    "iban": "DE89370400440532013000",
    "jwt_unlabelled": "c2lnbmF0dXJl",
}


# --------------------------------------------------------------------------- helpers


def _record(case: str, **values) -> None:
    METRICS.setdefault(case, {}).update(values)


@pytest.fixture
def env(tmp_path, monkeypatch):
    skills = {}
    for name, version in (("workflow-extract", "1.1.0"), ("skill-extractor", "1.0.0")):
        path = tmp_path / "skills" / name / "SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text(f"name: {name}\nversion: {version}\n", encoding="utf-8")
        skills[name] = path
    assert set(skills) == set(REQUIRED_SKILLS)
    monkeypatch.setenv("WORKFLOWHOOKER_SKILLS_ROOT", str(tmp_path / "skills"))
    root = tmp_path / "sessions"
    root.mkdir()
    return {"tmp": tmp_path, "root": root, "skills": skills}


def _controller(state: Path, budget: BudgetSpec | None = None) -> LifecycleController:
    return LifecycleController(
        CandidateSpool(state, max_records=500),
        extractor_version=EXTRACTOR_VERSION,
        privacy_class="local-private",
        budget=budget or BudgetSpec(),
    )


def _consumer(ctl: LifecycleController, env: dict, **kwargs) -> ExtractorConsumer:
    return ExtractorConsumer(ctl.spool, canonical_skill_paths=env["skills"], **kwargs)


def _transcript(env: dict, session_id: str, lines: list[str]) -> Path:
    path = env["root"] / "project" / f"{session_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for line in lines:
            handle.write(json.dumps({"type": "user", "message": line}, ensure_ascii=False) + "\n")
    return path


def _event(ctl, env, event: str, session_id: str, path: Path | None, *, now=None, **extra):
    payload = {"hook_event_name": event, "session_id": session_id, **extra}
    if path is not None:
        payload["transcript_path"] = str(path)
    return dispatch_shadow_lifecycle(
        ctl, provider="claude", event=event, payload=payload, session_root=env["root"], now=now
    )


class OracleRunner:
    """Faithful stand-in for a model applying the canonical skills.

    Emits a lesson only when a correction AND a verified fix are present,
    a workflow only on an explicit repetition marker, otherwise noop.
    """

    name = "s5-oracle"
    accepted_privacy_classes = frozenset({"local-private"})

    def __init__(self, *, vary: bool = False, echo_secret: str | None = None):
        self.calls = 0
        self.request_bytes: list[int] = []
        self.requests: list[dict] = []
        self.vary = vary
        self.echo_secret = echo_secret

    def run(self, request: dict, *, timeout_seconds: float) -> dict:
        self.calls += 1
        self.requests.append(request)
        size = len(json.dumps(request, ensure_ascii=False).encode("utf-8"))
        self.request_bytes.append(size)
        records = request["evidence_window"]["records"]
        correction = [r["evidence_id"] for r in records if "KORREKTUR" in r["text"]]
        fix = [r["evidence_id"] for r in records if "FIX-VERIFIZIERT" in r["text"]]
        repeat = [r["evidence_id"] for r in records if "WORKFLOW-WIEDERHOLT" in r["text"]]
        receipt = {
            "extractor_version": request["extractor_version"],
            "loaded_skills": request["canonical_skill_contracts"],
        }
        usage_in = size // 3
        usage = {"input_tokens": usage_in, "output_tokens": 200, "total_tokens": usage_in + 200}
        if correction and fix:
            kind, refs = "lesson", correction[:1] + fix[:1]
        elif len(repeat) >= 2:
            kind, refs = "workflow_candidate", repeat[:2]
        else:
            return {"result_type": "noop", "skill_receipt": receipt, "usage": usage}
        summary = "Korrektur und verifizierter Fix"
        if self.vary:
            summary += f" (Lauf {self.calls})"
        proposal = {"text": self.echo_secret} if self.echo_secret else {"text": "Regel anwenden"}
        return {
            "result_type": kind,
            "title": f"S5 {kind}",
            "summary": summary,
            "proposal": proposal,
            "evidence_refs": refs,
            "skill_receipt": receipt,
            "usage": usage,
        }


def _consume_all(ctl, env, runner, *, owner="s5", now=None) -> list:
    consumer = _consumer(ctl, env)
    return [
        consumer.consume(job.job_key, runner=runner, owner_id=owner, now=now)
        for job in ctl.spool.list_jobs()
    ]


# --------------------------------------------------------------------------- matrix


def test_no_evidence(env):
    ctl = _controller(env["tmp"] / "state")
    # (a) plain chat without learning signal -> model noop
    p = _transcript(env, "s-plain", ["Hallo", "Bitte Datei lesen", "Erledigt"])
    _event(ctl, env, "SessionEnd", "s-plain", p)
    runner = OracleRunner()
    results = _consume_all(ctl, env, runner)
    assert [r.action for r in results] == ["noop"]
    # (b) GoalComplete then SessionEnd with an explicit new horizon but no new bytes
    p2 = _transcript(env, "s-empty", ["Ziel erreicht"])
    _event(ctl, env, "GoalComplete", "s-empty", p2, goal_id="g1")
    _event(ctl, env, "SessionEnd", "s-empty", p2, horizon_hash="explicit-new-horizon")
    results = _consume_all(ctl, env, runner)
    actions = [r.action for r in results]
    stage0 = sum(1 for r in results if r.reason == "no-evidence")
    assert not ctl.spool.list_staged_candidates()
    _record(
        "no_evidence",
        jobs=len(ctl.spool.list_jobs()),
        staged=0,
        model_calls=runner.calls,
        stage0_noops=stage0,
        actions=actions,
        note="Kein deterministischer Stage-0-Signalfilter: jedes nichtleere Fenster ruft das Modell.",
    )


def test_correction_and_verified_fix(env):
    ctl = _controller(env["tmp"] / "state")
    p = _transcript(env, "s-fix", ["Mach X", "KORREKTUR: nicht X, sondern Y", "Y umgesetzt", "FIX-VERIFIZIERT: Tests gruen"])
    _event(ctl, env, "SessionEnd", "s-fix", p)
    runner = OracleRunner()
    results = _consume_all(ctl, env, runner)
    assert [r.action for r in results] == ["candidate"]
    staged = ctl.spool.list_staged_candidates()
    assert len(staged) == 1
    cand = staged[0]
    assert cand["candidate_type"] == "lesson"
    assert cand["review_required"] is True and cand["promotion_allowed"] is False
    import hashlib

    raw = p.read_bytes().split(b"\n")
    hashes = {hashlib.sha256(line).hexdigest() for line in raw if line}
    anchors_ok = all(a["event_hash"] in hashes for a in cand["evidence_anchors"])
    assert anchors_ok
    _record("correction_fix", staged=1, type=cand["candidate_type"], anchors_verified=anchors_ok, model_calls=runner.calls)


@pytest.mark.parametrize(
    "name,response",
    [
        ("hallucinated_ref", {"evidence_refs": ["ev-00000000000000000000"]}),
        ("extra_field", {"write_path": "C:/skills/x/SKILL.md"}),
        ("budget_lie", {"usage": {"input_tokens": 99_999, "output_tokens": 1, "total_tokens": 100_000}}),
        ("missing_skill_receipt", {"skill_receipt": None}),
        ("empty_refs", {"evidence_refs": []}),
    ],
)
def test_adversarial_runner_gate(env, name, response):
    ctl = _controller(env["tmp"] / "state")
    p = _transcript(env, "s-adv", ["KORREKTUR: a", "FIX-VERIFIZIERT: b"])
    _event(ctl, env, "SessionEnd", "s-adv", p)
    oracle = OracleRunner()

    class Adversary(OracleRunner):
        def run(self, request, *, timeout_seconds):
            base = oracle.run(request, timeout_seconds=timeout_seconds)
            base.update(response)
            return base

    results = _consume_all(ctl, env, Adversary())
    accepted = bool(ctl.spool.list_staged_candidates())
    assert not accepted and results[0].action == "failed"
    METRICS.setdefault("adversarial_gate", {"cases": 0, "false_accepts": 0, "reasons": {}})
    METRICS["adversarial_gate"]["cases"] += 1
    METRICS["adversarial_gate"]["false_accepts"] += int(accepted)
    METRICS["adversarial_gate"]["reasons"][name] = results[0].reason


def test_duplicate_events(env):
    ctl = _controller(env["tmp"] / "state")
    p = _transcript(env, "s-dup", ["KORREKTUR: a", "FIX-VERIFIZIERT: b"])
    sequential = [_event(ctl, env, "SessionEnd", "s-dup", p).action for _ in range(3)]
    p2 = _transcript(env, "s-dup-par", ["x"])
    out: list[str] = []
    threads = [
        threading.Thread(target=lambda: out.append(_event(ctl, env, "SessionEnd", "s-dup-par", p2).action))
        for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    jobs = ctl.spool.list_jobs()
    runner = OracleRunner()
    _consume_all(ctl, env, runner)
    _consume_all(ctl, env, runner)  # replay consume
    staged = ctl.spool.list_staged_candidates()
    assert len(jobs) == 2 and len(staged) == 1
    _record(
        "duplicate_events",
        events=11,
        jobs=len(jobs),
        staged=len(staged),
        duplicate_rate=round((len(jobs) - 2) / 2, 3),
        sequential_actions=sequential,
        parallel_actions=sorted(set(out)),
        model_calls=runner.calls,
    )


def test_goal_sessionend_overlap(env):
    ctl = _controller(env["tmp"] / "state")
    p = _transcript(env, "s-ov", ["KORREKTUR: a", "FIX-VERIFIZIERT: b"])
    g = _event(ctl, env, "GoalComplete", "s-ov", p, goal_id="goal-1")
    same = _event(ctl, env, "SessionEnd", "s-ov", p)
    _transcript(env, "s-ov", ["WORKFLOW-WIEDERHOLT 1", "WORKFLOW-WIEDERHOLT 2"])
    later = _event(ctl, env, "SessionEnd", "s-ov", p)
    jobs = sorted(ctl.spool.list_jobs(), key=lambda j: j.created_at)
    runner = OracleRunner()
    _consume_all(ctl, env, runner)
    staged = ctl.spool.list_staged_candidates()
    types = sorted(c["candidate_type"] for c in staged)
    windows = sorted((j.source_window_start, j.source_window_end) for j in ctl.spool.list_jobs())
    disjoint = windows[0][1] <= windows[1][0]
    assert same.action == "overlap-noop" and types == ["lesson", "workflow_candidate"] and disjoint
    _record(
        "goal_sessionend_overlap",
        actions=[g.action, same.action, later.action],
        jobs=len(jobs),
        staged_types=types,
        windows_disjoint=disjoint,
        duplicate_candidates=0,
    )


def test_compaction(env):
    ctl = _controller(env["tmp"] / "state")
    p = _transcript(env, "s-cmp", ["KORREKTUR: a", "FIX-VERIFIZIERT: b"])
    pre = _event(ctl, env, "PreCompact", "s-cmp", p)
    assert pre.action == "checkpointed" and not ctl.spool.list_jobs()
    _transcript(env, "s-cmp", ["[compact summary]", "weiter"])
    _event(ctl, env, "SessionEnd", "s-cmp", p)
    runner = OracleRunner()
    _consume_all(ctl, env, runner)
    append_staged = len(ctl.spool.list_staged_candidates())

    # Residual: a provider that REWRITES (shrinks) the transcript after a covered boundary.
    ctl2 = _controller(env["tmp"] / "state2")
    q = _transcript(env, "s-rw", ["KORREKTUR: a", "FIX-VERIFIZIERT: b", "fueller " * 40])
    _event(ctl2, env, "GoalComplete", "s-rw", q, goal_id="g1")
    _consume_all(ctl2, env, runner)
    q.write_text("", encoding="utf-8")
    _transcript(env, "s-rw", ["KORREKTUR: a", "FIX-VERIFIZIERT: b"])  # shorter rewrite
    _event(ctl2, env, "SessionEnd", "s-rw", q)
    _consume_all(ctl2, env, runner)
    rewrite_staged = [c["candidate_type"] for c in ctl2.spool.list_staged_candidates()]
    assert append_staged == 1
    _record(
        "compaction",
        precompact_action=pre.action,
        precompact_jobs=0,
        append_compaction_staged=append_staged,
        rewrite_shrink_staged=len(rewrite_staged),
        rewrite_duplicate_lessons=max(0, rewrite_staged.count("lesson") - 1),
        note="Schrumpfendes Transkript setzt das Fenster auf 0 zurueck; betrifft nur Provider, die das JSONL umschreiben.",
    )


def test_crash_before_candidate(env):
    ctl = _controller(env["tmp"] / "state")
    p = _transcript(env, "s-cb", ["KORREKTUR: a", "FIX-VERIFIZIERT: b"])
    _event(ctl, env, "SessionEnd", "s-cb", p, now=1_000.0)
    job = ctl.spool.list_jobs()[0]

    class Crashing(OracleRunner):
        def run(self, request, *, timeout_seconds):
            raise RuntimeError("runner crashed")

    first = _consumer(ctl, env).consume(job.job_key, runner=Crashing(), owner_id="a", now=1_001.0)
    # Hard kill while leased: lease held, nothing else written.
    lease = ctl.spool.lease(job.job_key, owner_id="killed", now=1_002.0, lease_seconds=10)
    blocked = _consumer(ctl, env).consume(job.job_key, runner=OracleRunner(), owner_id="b", now=1_003.0)
    rec = _event(ctl, env, "SessionStart", "s-cb", p, now=1_100.0)
    runner = OracleRunner()
    final = _consumer(ctl, env).consume(job.job_key, runner=runner, owner_id="c", now=1_101.0)
    assert first.action == "retryable" and lease.acquired and blocked.action == "leased"
    assert rec.action == "recovered" and final.action == "candidate"
    _record(
        "crash_before_candidate",
        runner_exception=first.reason,
        leased_during_kill=blocked.action,
        session_start=rec.action,
        recovered=final.action,
        staged=len(ctl.spool.list_staged_candidates()),
        recovery_rate=1.0,
    )


@pytest.mark.parametrize("vary", [False, True])
def test_crash_after_candidate(env, monkeypatch, vary):
    ctl = _controller(env["tmp"] / f"state-{vary}")
    p = _transcript(env, f"s-ca-{vary}", ["KORREKTUR: a", "FIX-VERIFIZIERT: b"])
    _event(ctl, env, "SessionEnd", f"s-ca-{vary}", p, now=2_000.0)
    job = ctl.spool.list_jobs()[0]
    runner = OracleRunner(vary=vary)
    real_finish = ctl.spool.finish

    def killed_finish(*a, **k):
        raise KeyboardInterrupt("process killed after staging")

    monkeypatch.setattr(ctl.spool, "finish", killed_finish)
    with pytest.raises(KeyboardInterrupt):
        _consumer(ctl, env).consume(job.job_key, runner=runner, owner_id="a", now=2_001.0)
    monkeypatch.setattr(ctl.spool, "finish", real_finish)
    rec = _event(ctl, env, "SessionStart", f"s-ca-{vary}", p, now=2_000.0 + 1_000)
    final = _consumer(ctl, env).consume(job.job_key, runner=runner, owner_id="b", now=3_001.0)
    staged = ctl.spool.list_staged_candidates()
    referenced = set(ctl.spool.load_receipt(job.job_key).candidate_ids)
    orphans = [c for c in staged if c["candidate_id"] not in referenced]
    assert rec.action == "recovered" and final.action == "candidate"
    _record(
        f"crash_after_candidate_{'nondeterministic' if vary else 'deterministic'}_runner",
        staged=len(staged),
        referenced=len(referenced),
        orphan_candidates=len(orphans),
        model_calls=runner.calls,
    )


def test_claude_sessionend_cancelled(env):
    ctl = _controller(env["tmp"] / "state")
    p = _transcript(env, "s-cancel", ["KORREKTUR: a", "FIX-VERIFIZIERT: b"])
    stop = _event(ctl, env, "Stop", "s-cancel", p)
    # SessionEnd hook cancelled -> never delivered. Resume of the same session:
    resume = _event(ctl, env, "SessionStart", "s-cancel", p)
    lost_without_goal = not ctl.spool.list_jobs()
    ctl2 = _controller(env["tmp"] / "state2")
    q = _transcript(env, "s-cancel-goal", ["KORREKTUR: a", "FIX-VERIFIZIERT: b"])
    _event(ctl2, env, "GoalComplete", "s-cancel-goal", q, goal_id="g1")
    covered_with_goal = len(ctl2.spool.list_jobs()) == 1
    assert lost_without_goal and covered_with_goal
    _record(
        "claude_sessionend_cancelled",
        stop_action=stop.action,
        resume_action=resume.action,
        session_lost_without_goal=lost_without_goal,
        covered_if_goal_completed=covered_with_goal,
        note="SessionStart holt nur abgelaufene Leases nach, keine verpassten SessionEnd-Grenzen.",
    )


def test_secret_pii_redaction(env):
    ctl = _controller(env["tmp"] / "state", BudgetSpec(max_tokens_per_job=50_000))
    lines = [f"Kontext {name}: {value}" for name, value in SECRETS.items()]
    lines += ["KORREKTUR: a", "FIX-VERIFIZIERT: b"]
    p = _transcript(env, "s-sec", lines)
    _event(ctl, env, "SessionEnd", "s-sec", p)
    echoed = " | ".join(SECRETS.values())
    runner = OracleRunner(echo_secret=echoed)
    results = _consume_all(ctl, env, runner)
    request_text = json.dumps(runner.requests[0], ensure_ascii=False)
    spool_text = "\n".join(
        f.read_text(encoding="utf-8") for f in (env["tmp"] / "state").rglob("*.json")
    )
    leaked_request = sorted(k for k, probe in SECRET_PROBES.items() if probe in request_text)
    leaked_spool = sorted(k for k, probe in SECRET_PROBES.items() if probe in spool_text)
    assert results[0].action == "candidate"
    _record(
        "secret_pii",
        secret_types=len(SECRETS),
        leaked_to_runner=leaked_request,
        leaked_to_staging=leaked_spool,
        runner_leak_rate=round(len(leaked_request) / len(SECRETS), 3),
        transcript_text_in_job_receipt=any(
            "Kontext" in f.read_text(encoding="utf-8")
            for f in (env["tmp"] / "state").rglob("*.json")
            if "staged" not in str(f)
        ),
    )


def test_budget(env):
    ctl = _controller(env["tmp"] / "state", BudgetSpec(max_tokens_per_job=12_000, max_jobs_per_session=1, max_jobs_per_day=2))
    p = _transcript(env, "s-b1", ["a"])
    first = _event(ctl, env, "GoalComplete", "s-b1", p, goal_id="g1", now=10_000.0)
    _transcript(env, "s-b1", ["b"])
    second = _event(ctl, env, "SessionEnd", "s-b1", p, now=10_001.0)
    other = [
        _event(ctl, env, "SessionEnd", sid, _transcript(env, sid, ["c"]), now=10_002.0).action
        for sid in ("s-b2", "s-b3")
    ]
    ctl_tok = _controller(env["tmp"] / "state-tok", BudgetSpec(max_tokens_per_job=100))
    q = _transcript(env, "s-tok", ["KORREKTUR: a" * 50, "FIX-VERIFIZIERT: b"])
    _event(ctl_tok, env, "SessionEnd", "s-tok", q)
    runner = OracleRunner()
    tok = _consume_all(ctl_tok, env, runner)
    assert first.action == "enqueued" and second.action == "deferred"
    _record(
        "budget",
        session_budget=[first.action, second.action, second.reason],
        daily_budget=other,
        token_budget=[r.reason for r in tok],
        model_calls_under_token_budget=runner.calls,
    )


def test_repo_lock_and_no_foreign_writes(env):
    repo = env["tmp"] / "repo"
    (repo / "skills" / "x").mkdir(parents=True)
    (repo / "LOCK.user.txt").write_text("gesperrt", encoding="utf-8")
    (repo / "skills" / "x" / "SKILL.md").write_text("name: x\n", encoding="utf-8")
    watched = [repo, *[s.parent for s in env["skills"].values()], env["root"]]

    def snapshot():
        return {
            str(f): f.read_bytes()
            for base in watched
            for f in sorted(base.rglob("*"))
            if f.is_file()
        }

    ctl = _controller(env["tmp"] / "state")
    p = _transcript(env, "s-lock", ["KORREKTUR: a", "FIX-VERIFIZIERT: b"])
    before = snapshot()
    _event(ctl, env, "SessionEnd", "s-lock", p)
    _consume_all(ctl, env, OracleRunner())
    after = snapshot()
    assert before == after
    _record(
        "repo_lock_cooldown",
        foreign_files_changed=0,
        writes_outside_spool=False,
        note="Kein Writer ausser Staging vorhanden; Repo-Lock/Cooldown-Gate existiert noch nicht und ist erst mit einem Promoter noetig.",
    )


def test_rollback_disabled_and_fail_open(env, monkeypatch, capsys):
    p = _transcript(env, "s-rb", ["x"])
    payload = {"hook_event_name": "SessionEnd", "session_id": "s-rb", "transcript_path": str(p)}
    results = {}
    for label, cfg_text, stdin in (
        ("disabled", "[candidates]\nenabled = false\n", json.dumps(payload)),
        ("malformed_payload", "[candidates]\nenabled = true\n", "{kaputt"),
        ("foreign_path", "[candidates]\nenabled = true\n", json.dumps({**payload, "transcript_path": str(env["tmp"] / "x.jsonl")})),
    ):
        cfg = env["tmp"] / f"{label}.toml"
        cfg.write_text(cfg_text, encoding="utf-8")
        state = env["tmp"] / f"state-{label}"
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        code = main(["--config", str(cfg), "--state-dir", str(state), "provider-shadow", "claude", "SessionEnd", "--session-root", str(env["root"])])
        results[label] = {"exit": code, "jobs": len(CandidateSpool(state).list_jobs()), "stdout": capsys.readouterr().out}
    assert all(r["exit"] == 0 and r["jobs"] == 0 and r["stdout"] == "" for r in results.values())
    with pytest.raises(ProviderPayloadError):
        _event(_controller(env["tmp"] / "s"), env, "SessionEnd", "other", p)
    _record("rollback_fail_open", **results)


def test_usmc_bridge_signals(env):
    usmc_client = pytest.importorskip("usmc.client")
    pytest.importorskip("usmc.lesson_contract")
    ctl = _controller(env["tmp"] / "state")
    p = _transcript(env, "s-usmc", ["KORREKTUR: a", "FIX-VERIFIZIERT: b"])
    _event(ctl, env, "SessionEnd", "s-usmc", p)
    _consume_all(ctl, env, OracleRunner())
    cand = ctl.spool.list_staged_candidates()[0]
    db = usmc_client.USMCClient(db_path=env["tmp"] / "usmc.db", agent_id="s5")
    kwargs = dict(
        title=cand["title"], problem=cand["summary"], solution=json.dumps(cand["proposal"], ensure_ascii=False),
        source_kind="agent", source_key="workflowhooker:claude", episode_key=cand["candidate_id"],
        source_hash=cand["window_hash"], event_anchor=cand["evidence_anchors"][0]["event_hash"],
        evidence_class="verified", privacy_scope="local",
    )
    first = db.add_lesson(**kwargs)
    retry = db.add_lesson(**kwargs)
    lid = first["id"]
    w0 = db.get_lesson(lid).get("weight", db.get_lesson(lid).get("confidence"))
    db.record_lesson_feedback(lid, "fb-1", helpful=True)
    db.record_lesson_feedback(lid, "fb-1", helpful=True)
    db.record_lesson_feedback(lid, "fb-2", independent_repeat=True, delivery_failed=True)
    row = db.get_lesson(lid)
    gate_off = db.evaluate_lesson_promotion(lid)
    gate_on = db.evaluate_lesson_promotion(lid, direct_promotion_enabled=True)
    pref = db.add_lesson(**{**kwargs, "episode_key": cand["candidate_id"] + "-pref", "user_preference": True})
    pref_gate = db.evaluate_lesson_promotion(pref["id"], direct_promotion_enabled=True)
    draft_delivery = db.deliver_lessons("sess", "dk-1", lesson_ids=[lid])
    assert retry.get("created") is False and row["helpful_count"] == 1
    assert gate_off["allowed"] is False and gate_on["allowed"] is True and pref_gate["allowed"] is False
    _record(
        "usmc_helpful_repeat_delivery",
        ingest_created=first.get("created"),
        retry_created=retry.get("created"),
        initial_weight=w0,
        helpful_count=row["helpful_count"],
        independent_repeat_count=row["independent_repeat_count"],
        delivery_failure_count=row["delivery_failure_count"],
        gate_disabled_allowed=gate_off["allowed"],
        gate_enabled_allowed=gate_on["allowed"],
        user_preference_review_reasons=pref_gate["review_reasons"],
        draft_lessons_delivered=len(draft_delivery),
        note="Bruecke Kandidat->USMC existiert nur in diesem Harness, nicht im Produktcode.",
    )


def test_zz_write_report():
    target = os.environ.get("WFL_S5_REPORT")
    if target:
        Path(target).write_text(json.dumps(METRICS, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
