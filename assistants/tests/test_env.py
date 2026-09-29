import os

from assistants import env


def test_values_are_loaded_without_overriding(monkeypatch, tmp_path):
    monkeypatch.delenv("LG_TEST_A", raising=False)
    monkeypatch.delenv("LG_TEST_C", raising=False)
    monkeypatch.setenv("LG_TEST_B", "from the terminal")
    path = tmp_path / ".env"
    path.write_text(
        '# comment\n\nLG_TEST_A="quoted value"\n'
        "export LG_TEST_B=from the file\nLG_TEST_C=\nnot a line\n",
        encoding="utf-8",
    )
    env.load(path)
    assert os.environ["LG_TEST_A"] == "quoted value"
    assert os.environ["LG_TEST_B"] == "from the terminal"
    # An empty value (a key not pasted yet) sets nothing.
    assert "LG_TEST_C" not in os.environ


def test_a_missing_file_changes_nothing(tmp_path):
    before = dict(os.environ)
    env.load(tmp_path / "absent.env")
    assert dict(os.environ) == before


def test_the_default_file_is_the_one_tests_point_at(tmp_path):
    assert env.ENV_FILE.name == "missing.env"
