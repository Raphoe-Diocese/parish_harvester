"""Ensure permanent bulletin links can be compared by downloaded file bytes."""
from harvester.bulletin_freshness import pdf_sha256, bulletin_size_changed


def test_same_url_same_size_changed_pdf_bytes_are_detectable(tmp_path):
    previous = tmp_path / "previous.pdf"
    current = tmp_path / "current.pdf"
    previous.write_bytes(b"%PDF-1.4\nweekly bulletin A\n")
    current.write_bytes(b"%PDF-1.4\nweekly bulletin B\n")
    assert previous.stat().st_size == current.stat().st_size
    assert not bulletin_size_changed(previous.stat().st_size, current.stat().st_size)
    assert pdf_sha256(previous) != pdf_sha256(current)


def test_identical_downloaded_pdf_has_same_fingerprint(tmp_path):
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    data = b"%PDF-1.4\nunchanged permanent bulletin\n"
    first.write_bytes(data)
    second.write_bytes(data)
    assert pdf_sha256(first) == pdf_sha256(second)


def test_missing_file_does_not_produce_fingerprint(tmp_path):
    assert pdf_sha256(tmp_path / "missing.pdf") is None
