from __future__ import annotations

from mmc.cli import main


def test_run_vendor_disclosure(capsys, tmp_db, monkeypatch) -> None:
    monkeypatch.setenv("MMC_DB_PATH", str(tmp_db))
    code = main(["run", "hello", "--seed", "1"])
    assert code == 0
    err = capsys.readouterr().err
    assert "Sending prompt to:" in err


def test_clear_without_yes() -> None:
    assert main(["clear", "--all"]) == 2
