from omai.memory import MemoryStore


def test_add_search_delete(tmp_path):
    m = MemoryStore(tmp_path / "m.db")
    a = m.add("My sister Priya lives in Pune")
    b = m.add("I prefer answers in bullet points")
    assert m.count() == 2

    hits = m.search("where does my sister live")
    assert [h.id for h in hits] == [a]

    assert m.delete(a) is True
    assert m.search("sister") == []          # FTS index cleaned up on delete
    assert m.get(b) is not None
    assert m.delete(a) is False


def test_dedup_and_whitespace(tmp_path):
    m = MemoryStore(tmp_path / "m.db")
    a = m.add("Likes  tea")
    b = m.add("likes tea")
    assert a == b and m.count() == 1


def test_search_is_safe_against_fts_syntax(tmp_path):
    m = MemoryStore(tmp_path / "m.db")
    m.add("password manager is Bitwarden")
    for nasty in ['"', "AND OR NOT", "foo* NEAR(", "'; DROP TABLE memories; --", "***", ""]:
        m.search(nasty)  # must not raise
    assert m.count() == 1


def test_prefix_and_ranking(tmp_path):
    m = MemoryStore(tmp_path / "m.db")
    m.add("Meeting with the accountant every Friday")
    best = m.add("Accounting software is Tally; accountant is Rahul")
    hits = m.search("accountant tally")
    assert hits[0].id == best


def test_empty_rejected(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        MemoryStore(tmp_path / "m.db").add("   ")


def test_files_are_owner_only(tmp_path):
    import stat
    MemoryStore(tmp_path / "sub" / "m.db")
    mode = stat.S_IMODE((tmp_path / "sub" / "m.db").stat().st_mode)
    assert mode == 0o600
