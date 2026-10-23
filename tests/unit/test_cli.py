from __future__ import annotations

import json

from mmc.cli import main


def test_run_vendor_disclosure_mock(capsys, tmp_db, monkeypatch) -> None:
    monkeypatch.setenv("MMC_DB_PATH", str(tmp_db))
    code = main(["run", "hello", "--seed", "1"])
    assert code == 0
    err = capsys.readouterr().err
    assert "Mock mode: nothing is sent to any provider" in err


def test_run_prints_scores_and_timing(capsys, tmp_db, monkeypatch) -> None:
    monkeypatch.setenv("MMC_DB_PATH", str(tmp_db))
    code = main(["run", "hello", "--seed", "1"])
    assert code == 0
    out = capsys.readouterr().out
    assert "ttft_ms=" in out
    assert "total_ms=" in out
    assert "cost_usd=" in out
    assert "judge_score" in out


def test_run_validation_error_stderr(capsys, tmp_db, monkeypatch) -> None:
    monkeypatch.setenv("MMC_DB_PATH", str(tmp_db))
    code = main(["run", ""])
    assert code == 2
    err = capsys.readouterr().err
    assert "error:" in err
    assert "prompt" in err


def test_clear_without_yes() -> None:
    assert main(["clear", "--all"]) == 2


def test_clear_with_yes(tmp_db, monkeypatch, capsys) -> None:
    monkeypatch.setenv("MMC_DB_PATH", str(tmp_db))
    assert main(["run", "one", "--seed", "1"]) == 0
    capsys.readouterr()
    assert main(["clear", "--all", "--yes"]) == 0
    assert main(["history", "--json"]) == 0


def test_history_json(tmp_db, monkeypatch, capsys) -> None:
    monkeypatch.setenv("MMC_DB_PATH", str(tmp_db))
    main(["run", "hist", "--seed", "2"])
    capsys.readouterr()
    main(["history", "--limit", "5", "--json"])
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) >= 1


def test_show_and_export(tmp_db, monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("MMC_DB_PATH", str(tmp_db))
    main(["run", "show me", "--seed", "3", "--json"])
    run_id = json.loads(capsys.readouterr().out)["id"]
    assert main(["show", run_id, "--json"]) == 0
    out_json = tmp_path / "out.json"
    out_csv = tmp_path / "out.csv"
    assert main(["export", "--format", "json", "--out", str(out_json)]) == 0
    assert main(["export", "--format", "csv", "--out", str(out_csv)]) == 0
    assert out_json.stat().st_size > 0
    assert out_csv.stat().st_size > 0
