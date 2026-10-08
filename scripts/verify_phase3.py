"""Synthetic smoke report with real trained inference and visible false positives."""

import base64
import json

import cv2
import numpy as np
from app.layers.l3_tampering.analyzer import analyze_tampering, overlay
from app.layers.l3_tampering.synthetic import ATTACKS, make_variant
from app.settings import ROOT


def main() -> None:
    output = ROOT / "reports" / "phase3_visuals"
    output.mkdir(parents=True, exist_ok=True)
    reports, panels = {}, []
    for attack in ATTACKS:
        image, mask = make_variant(8, attack)
        payload = cv2.imencode(".jpg", image)[1].tobytes()
        result = analyze_tampering(payload, (127 / 192, 30 / 192, 53 / 192, 88 / 192))
        reports[attack] = result.model_dump(mode="json")
        heatmaps = {}
        for key in (
            "heatmap_png_base64",
            "overlay_png_base64",
            "cnn_heatmap_png_base64",
        ):
            value = reports[attack]["data"].pop(key)
            if value:
                decoded = base64.b64decode(value)
                (output / f"{attack}_{key.replace('_png_base64', '')}.png").write_bytes(
                    decoded
                )
                heatmaps[key] = cv2.imdecode(
                    np.frombuffer(decoded, np.uint8), cv2.IMREAD_COLOR
                )
        cnn = heatmaps.get("cnn_heatmap_png_base64")
        if cnn is not None:
            cnn = overlay(image, cnn[:, :, 0].astype(np.float32) / 255)
        else:
            cnn = image.copy()
        row = np.concatenate(
            [
                image,
                cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR),
                heatmaps["overlay_png_base64"],
                cnn,
            ],
            axis=1,
        )
        label = np.full((30, row.shape[1], 3), 245, np.uint8)
        cv2.putText(
            label,
            attack + " | input / truth / classical / CNN",
            (8, 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (20, 20, 20),
            1,
        )
        panels.append(np.concatenate([label, row], axis=0))
        print(
            f"{attack}: baseline={result.data.suspicion_score:.3f}, "
            f"{result.duration_ms:.0f}ms"
        )
    cv2.imwrite(str(output / "comparison.png"), np.concatenate(panels, axis=0))
    (ROOT / "reports" / "phase3_smoke.json").write_text(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
