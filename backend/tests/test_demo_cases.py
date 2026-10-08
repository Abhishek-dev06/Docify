import numpy as np
from app.demo_cases import demo_case
from app.layers.l0_capture.preprocess import decode_image
from app.main import app
from fastapi.testclient import TestClient


def test_photo_replacement_changes_only_document_portrait():
    original, live_a, _ = demo_case("genuine")
    replaced, live_again, truth = demo_case("photo_replaced")
    a, b = decode_image(original), decode_image(replaced)
    assert live_a == live_again
    differences = np.any(a != b, axis=2)
    assert differences[245:555, 1200:1510].any()
    differences[245:555, 1200:1510] = False
    assert not differences.any()
    assert truth["scenario"] == "photo_replaced"


def test_demo_route_serves_new_case_and_rejects_unknown_case():
    with TestClient(app) as client:
        response = client.get("/api/v1/demo/fixtures/photo_replaced/document")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert decode_image(response.content).shape == (1000, 1600, 3)
        assert client.get("/api/v1/demo/fixtures/unknown/document").status_code == 422
