"""Measure safe, repeatable wall-clock metrics for Axmed's deployed OCR service."""

import argparse
import base64
import json
import os
import statistics
import time
from pathlib import Path
from urllib.request import Request, urlopen


def percentile(values: list[float], fraction: float) -> float:
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def request_ocr(endpoint: str, token: str, path: Path, request_number: int) -> dict[str, object]:
    media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    payload = json.dumps(
        {
            "schema_version": "1.0",
            "media_type": media_type,
            "content_base64": base64.b64encode(path.read_bytes()).decode("ascii"),
            "selected_original_pages": [1],
            "idempotency_key": f"benchmark-{path.stem}-{request_number}",
            "deadline_ms": 120_000,
        }
    ).encode("utf-8")
    request = Request(
        endpoint,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    started = time.perf_counter()
    with urlopen(request, timeout=130) as response:  # noqa: S310 - operator-supplied Axmed service URL.
        result = json.loads(response.read().decode("utf-8"))
    wall_duration_ms = (time.perf_counter() - started) * 1000
    pages = result["pages"]
    return {
        "wall_duration_ms": round(wall_duration_ms, 2),
        "provider_duration_ms": result["duration_ms"],
        "page_count": len(pages),
        "line_count": sum(len(page["lines"]) for page in pages),
        "provider": result["provider"],
        "model": result["model"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--endpoint", default=os.environ.get("AXMED_OCR_SERVICE_URL"))
    parser.add_argument("--token", default=os.environ.get("AXMED_OCR_SERVICE_TOKEN"))
    args = parser.parse_args()
    if not args.endpoint or not args.token:
        parser.error("AXMED_OCR_SERVICE_URL and AXMED_OCR_SERVICE_TOKEN are required.")
    if args.runs < 1:
        parser.error("--runs must be at least 1.")
    if not args.file.is_file():
        parser.error("file does not exist.")

    samples = [request_ocr(args.endpoint, args.token, args.file, index + 1) for index in range(args.runs)]
    wall_times = [float(sample["wall_duration_ms"]) for sample in samples]
    provider_times = [float(sample["provider_duration_ms"]) for sample in samples]
    print(
        json.dumps(
            {
                "file": args.file.name,
                "runs": args.runs,
                "provider": samples[0]["provider"],
                "model": samples[0]["model"],
                "page_count": samples[0]["page_count"],
                "line_count": samples[0]["line_count"],
                "wall_ms": {"p50": round(statistics.median(wall_times), 2), "p95": round(percentile(wall_times, 0.95), 2)},
                "provider_ms": {
                    "p50": round(statistics.median(provider_times), 2),
                    "p95": round(percentile(provider_times, 0.95), 2),
                },
            }
        )
    )


if __name__ == "__main__":
    main()
