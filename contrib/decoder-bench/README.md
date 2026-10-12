# Opt-in Vorbis decoder experiment

This standalone harness compares the actual local `librespot-playback` decoder
with and without Symphonia's optional SIMD transform. Its own workspace and
lockfile isolate the experiment from production defaults. Both executables use
the same `../../playback` source; only the harness's `simd` feature differs.
It opens no audio device, authenticates no session and reads no application
configuration. The experiment is intended for macOS/Linux; the recorded run
used macOS arm64, Rust 1.92.0, Python 3 and FFmpeg 8.1.1.

From this directory, after ensuring that other profiling or build work is idle:

```sh
cargo build --release --locked
mkdir -p bin
cp target/release/decoder-bench bin/scalar
cargo build --release --locked --features simd
cp target/release/decoder-bench bin/simd
python3 generate_fixture.py
python3 compare.py --verify-only
python3 compare.py --pairs 5 --passes 200
```

Add `--offline` to the Cargo commands when the locked dependencies are cached.
Build output defaults to this standalone workspace's `target` directory; unset
`CARGO_TARGET_DIR` or adjust the copy commands if using a custom target directory.
No absolute-path dependency overrides are needed. Do not enable SIMD in the
production manifest before the scalar build: that would invalidate the comparison.

The `simd` feature enables `symphonia/opt-simd` only for this experiment, including
RustFFT's NEON, SSE and AVX support with runtime dispatch and scalar fallback.
No `target-cpu=native` flag is used. SIMD can also change which scalar transform
backend runs on unsupported architectures; this experiment does not validate
performance or numerical behavior on every platform. It adds five resolved
packages: RustFFT, num-complex, primal-check, strength_reduce and transpose.

## Fixture and two regression contracts

`generate_fixture.py` creates its output directory and produces original,
deterministic 16-second stereo 44.1 kHz PCM with separate left/right synthesized
chords, noise transients and a silent interval. It encodes that PCM with FFmpeg's
native experimental Vorbis encoder at a requested 160 kbps. Container bytes can
vary between encodes. No source audio is downloaded or recorded.

The observed FFmpeg 8.1.1 output averaged about 151 kbps and contained mostly
1024-frame packets plus a 64-frame tail. It does **not** cover short/long Vorbis
block transitions or establish equivalence to a music service's encoder.

The comparator enforces two contracts:

1. Complete decoding produces exactly 705,600 stereo frames (1,411,200 scalar
   samples), identical per-packet positions, lengths and skipped markers, and
   finite PCM in both builds.
2. Seeking back from EOF to 5,731 ms returns the same position and produces
   equivalent remaining PCM and packet metadata in both builds.

Both comparisons require maximum absolute sample difference ≤1e-5 and RMS
difference ≤1e-6 to accommodate f32 transform rounding. Actual errors are saved
in `results/verification.json` or `results/comparison.json`. These checks do not
claim bit identity or perceptual conformance. Successful comparison removes the
temporary PCM dumps; all generated files, fixtures, binaries and caches are ignored.

## CPU measurement

Encoded bytes are loaded into memory before timing, and each process performs
two untimed full decodes. A timed pass constructs the actual `SymphoniaDecoder`
and decodes the entire fixture, retaining its packet allocations and f64
conversion. Sample consumption is black-boxed. File writes and per-sample
comparison are outside the timed region; network, output, player volume
processing, UI and spectrum analysis are not measured.

The process CPU clock counts user and system CPU time across all threads.
`realtime_cpu_percent = 100 * cpu_seconds / decoded_audio_seconds`, where 100%
means one CPU core continuously needed to decode in real time. The benchmark
runs as fast as possible, so this is not its instantaneous CPU percentage.
Wall time is reported separately. Five pairs alternate scalar/SIMD ordering;
raw observations and medians are saved in `results/comparison.json`.

The initial synthetic run found a 12.52% decoder-only reduction but only about
0.00946 percentage points of one core in absolute savings. That small result
does not establish a meaningful whole-application improvement and is why SIMD
remains an opt-in experiment. The output queue, buffering, latency, transport
controls and dropout behavior are not changed or validated here.

The harness is MIT-licensed with librespot. Retain dependency attribution:
Symphonia is MPL-2.0; RustFFT is MIT OR Apache-2.0.
