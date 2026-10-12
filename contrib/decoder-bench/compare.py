#!/usr/bin/env python3
"""Two regression contracts and alternated CPU runs of the actual decoder."""
import argparse
import array
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--passes", type=int, default=200)
parser.add_argument("--pairs", type=int, default=5)
parser.add_argument("--verify-only", action="store_true")
args = parser.parse_args()
fixture = root / "fixtures/synthetic.ogg"
results = root / "results"
results.mkdir(exist_ok=True)
binaries = {name: root / f"bin/{name}" for name in ("scalar", "simd")}

def invoke(name, mode, value):
    return json.loads(subprocess.check_output([str(binaries[name]), mode, str(fixture), str(value), name], text=True))

def read_pcm(path):
    values = array.array("d")
    with path.open("rb") as source:
        values.frombytes(source.read())
    if sys.byteorder != "little":
        values.byteswap()
    return values

seek = {name: invoke(name, "dump", results / name) for name in binaries}
assert seek["scalar"]["seek_returned_ms"] == seek["simd"]["seek_returned_ms"], seek
checks = {}
for contract in ("full", "seek"):
    left = results / f"scalar.{contract}"
    right = results / f"simd.{contract}"
    assert left.with_suffix(f".{contract}.tsv").read_bytes() == right.with_suffix(f".{contract}.tsv").read_bytes(), "packet positions or lengths differ"
    a = read_pcm(Path(f"{left}.f64le"))
    b = read_pcm(Path(f"{right}.f64le"))
    assert len(a) == len(b) and len(a) > 0, "sample counts differ"
    if contract == "full":
        assert len(a) == 16 * 44100 * 2, "expected exactly 705,600 stereo frames"
    errors = [abs(x - y) for x, y in zip(a, b)]
    maximum = max(errors)
    rms = math.sqrt(sum(x*x for x in errors) / len(errors))
    assert maximum <= 1e-5 and rms <= 1e-6, (contract, maximum, rms)
    checks[contract] = {"samples": len(a), "max_abs_error": maximum, "rms_error": rms,
                        "packet_metadata_equal": True, "all_finite": True}
    Path(f"{left}.f64le").unlink()
    Path(f"{right}.f64le").unlink()
report = {"verification": checks, "seek": seek, "runs": []}
print(json.dumps({"verification": checks, "seek": seek}), flush=True)
if not args.verify_only:
    for pair in range(args.pairs):
        order = ("scalar", "simd") if pair % 2 == 0 else ("simd", "scalar")
        for name in order:
            run = invoke(name, "bench", args.passes)
            run["pair"] = pair
            report["runs"].append(run)
            print(json.dumps(run), flush=True)
    medians = {name: statistics.median(r["realtime_cpu_percent"] for r in report["runs"] if r["label"] == name) for name in binaries}
    report["median_realtime_cpu_percent"] = medians
    report["median_cpu_reduction_percent"] = (1 - medians["simd"] / medians["scalar"]) * 100
    print(json.dumps({"medians": medians, "reduction_percent": report["median_cpu_reduction_percent"]}), flush=True)
(results / ("verification.json" if args.verify_only else "comparison.json")).write_text(json.dumps(report, indent=2) + "\n")
