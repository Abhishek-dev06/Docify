"""Dataset label integrity, leakage prevention and bounded download behavior."""

import hashlib
import importlib.util
import json
from io import BytesIO

import cv2
import pytest
from app.layers.l3_tampering.synthetic import make_variant
from app.settings import ROOT


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def data_manifest(tmp_path, rows):
    image, mask = make_variant(3, "text_replacement")
    cv2.imwrite(str(tmp_path / "image.png"), image)
    cv2.imwrite(str(tmp_path / "mask.png"), mask)
    manifest = tmp_path / "input.json"
    manifest.write_text(json.dumps(rows))
    return manifest


def test_prepare_keeps_mask_alignment_and_records_provenance(tmp_path):
    rows = [
        {
            "image": "image.png",
            "mask": "mask.png",
            "group": "document-1",
            "attack": "text_replacement",
            "split": "train",
        }
    ]
    source = data_manifest(tmp_path, rows)
    result = script("prepare_tamper_dataset").prepare(
        tmp_path, source, tmp_path / "out"
    )
    assert result[0]["split"] == "train"
    assert len(result[0]["source_sha256"]) == 64
    assert cv2.imread(str(tmp_path / "out" / result[0]["mask"])).any()


def test_prepare_unknown_is_never_clean(tmp_path):
    rows = [{"image": "image.png", "group": "x", "attack": "unknown"}]
    source = data_manifest(tmp_path, rows)
    with pytest.raises(ValueError, match="Unknown labels"):
        script("prepare_tamper_dataset").prepare(tmp_path, source, tmp_path / "out")


def test_prepare_rejects_duplicate_pixels_across_splits(tmp_path):
    rows = [
        {
            "image": "image.png",
            "mask": "mask.png",
            "group": group,
            "attack": "text_replacement",
            "split": split,
        }
        for group, split in [("a", "train"), ("b", "test")]
    ]
    source = data_manifest(tmp_path, rows)
    with pytest.raises(ValueError, match="Identical decoded image"):
        script("prepare_tamper_dataset").prepare(tmp_path, source, tmp_path / "out")


def test_prepare_rejects_escape_paths(tmp_path):
    with pytest.raises(ValueError, match="inside"):
        script("prepare_tamper_dataset").inside(tmp_path, "../outside.png")


def test_download_budget_rejects_before_network(tmp_path, monkeypatch):
    module = script("download_datasets")
    monkeypatch.setattr(
        module.urllib.request, "urlopen", lambda *a, **k: pytest.fail("network")
    )
    with pytest.raises(ValueError, match="budget"):
        module.download(
            "https://example.invalid/file",
            tmp_path / "large.zip",
            "0" * 32,
            max_bytes=100,
            minimum_bytes=1000,
        )


@pytest.mark.parametrize("valid", [True, False])
def test_download_checksum_and_atomic_output(tmp_path, monkeypatch, valid):
    module = script("download_datasets")
    body = b"mock dataset content"
    response = BytesIO(body)
    response.headers = {"Content-Length": str(len(body))}
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *a, **k: response)
    destination = tmp_path / "sample.zip"
    md5 = hashlib.md5(body, usedforsecurity=False).hexdigest() if valid else "0" * 32
    if valid:
        result = module.download("https://example.invalid", destination, md5, 100)
        assert destination.read_bytes() == body and result["bytes"] == len(body)
    else:
        with pytest.raises(ValueError, match="checksum"):
            module.download("https://example.invalid", destination, md5, 100)
        assert not destination.exists()
    assert not destination.with_suffix(".zip.partial").exists()


def test_existing_partial_is_preserved(tmp_path):
    part = tmp_path / "sample.zip.partial"
    part.write_bytes(b"existing")
    with pytest.raises(ValueError, match="Partial"):
        script("download_datasets").download(
            "https://example.invalid", tmp_path / "sample.zip", "0" * 32, 100
        )
    assert part.read_bytes() == b"existing"
