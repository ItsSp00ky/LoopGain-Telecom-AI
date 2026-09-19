import pytest

from prepaid_churn.cli import main


def test_help_exits_cleanly(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "churn" in capsys.readouterr().out


def test_no_command_prints_help(capsys):
    main([])
    assert "usage: churn" in capsys.readouterr().out


def test_profile_writes_report(raw, tmp_path):
    source = tmp_path / "train.csv"
    raw.to_csv(source, index=False)
    output = tmp_path / "reports" / "profile.md"
    main(["profile", "--input", str(source), "--output", str(output)])
    assert output.read_text(encoding="utf-8").startswith("# T1 data profile")


def test_profile_missing_input_fails_cleanly(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["profile", "--input", str(tmp_path / "missing.csv")])
    assert exc.value.code == 1
    assert "README" in capsys.readouterr().err
