# macOS playback investigation: SIMD is not the application fix

The measured Symphonia SIMD experiment reduced synthetic Vorbis decoder CPU by
12.52%, but saved only **0.00946 percentage points of one CPU core** at real-time
playback rate. The benchmark executable grew by 460,928 bytes. That result does
not justify enabling the feature by default to address an application using
roughly 3–4% CPU in the background. This branch retains a reproducible opt-in
experiment and two decoding checks; it changes no production features or audio
behavior.

## Provenance and scope

The caller locks crates.io `librespot` and `librespot-playback` 0.8.0. Published
crate VCS metadata identifies upstream commit
`d36f9f1907e8cc9d68a93f8ebc6b627b1bf7267d`, the `v0.8.0` tag in
[librespot-org/librespot](https://github.com/librespot-org/librespot/tree/v0.8.0).
This branch and its comparison base start at that commit, not upstream `dev`.
Upstream MIT licensing and attribution remain intact.

Measurements were made on 2026-10-12, macOS 26.7.1 (25G241), Mac14,6, 12 logical
CPUs, arm64, with Rust/Cargo 1.92.0. The installed caller's Mach-O UUID matched
its local release build, and its existing signature verified. The application
and its production dependency were not rebuilt or replaced. Private source,
music, credentials, account data, raw stack dumps and screenshots are excluded
from this repository.

## Live baseline

CPU is the change in cumulative process user+system CPU time from `ps`, divided
by monotonic elapsed wall time. **100% means one logical core**, not the whole
12-core machine. Each repeated window was approximately 30.12 seconds. Target
process IDs remained stable. No compilation or stack profiler ran during these
windows. The Spotify total includes its main executable and all helpers under
its app bundle, including its orphaned helper; unrelated applications are
excluded.

| State | Window 1, % one core | Window 2, % one core |
|---|---:|---:|
| Liner Notes, minimized, playing, spectrum enabled | 4.3820 | 4.4156 |
| Liner Notes, minimized, playing, spectrum disabled | 3.2528 | 3.3526 |
| Spotify full app process tree, minimized, playing | 2.6901 | 2.5891 |
| Liner Notes minimized and paused during Spotify windows | 1.5277 | 1.5269 |

Both applications played the same catalog recording, after playback settled.
These were sequential portions of the track, not identical decoded segments.
Existing per-app volumes were preserved. Spectrum was temporarily disabled only
to attribute its cost, then restored. The settings and theme files matched their
original hashes afterward. The first spectrum-off window overlaps inspection of
Spotify's settings UI; its target process CPU was not included in the Liner Notes
number. These short observations establish a gap, not a population estimate.

The live caller stack confirms Vorbis decoding. Its configuration requests the
default 160 kbps and disables normalization; the actual selected fallback
bitrate was not directly observed. Spotify's UI showed Automatic streaming
quality, automatic quality adjustment enabled, and Normal volume normalization.
Its actual codec and bitrate were not observable. Consequently this is not a
controlled comparison of identical decoder quality/settings. No setting was
changed to make one application win.

In this run Spotify's main process accounted for 2.4576% and 2.4232%; all helpers
together accounted for 0.2325% and 0.1660%. A single helper is not a reliable
measure of the whole application's cost. This does not invalidate a different
process layout or earlier observation.

## Hotspot attribution

Two separate 10-second, 1 ms `sample` captures were taken. These sample all
threads, including sleeping threads. Counts below are wall-sample observations,
**not percentages of CPU time**, and stacks must not be summed recursively.

- With the large window visible and spectrum enabled, 6,537 of 7,323 main-thread
  samples were in the draw path; 5,052 were in software-buffer presentation and
  3,702 descended into macOS image color conversion. Exploratory process CPU
  windows were about 80–81%; one overlapped profiling/tool startup, so those are
  not controlled comparison numbers. The visible-window problem belongs to the
  caller's rendering/presentation path, not librespot's decoder.
- With the window hidden and spectrum disabled, 7,900 of 7,954 main-thread
  samples were waiting for events. The player thread had 41 observations in
  decoding, including the scalar Vorbis IMDCT/FFT. Its other dominant stack was
  the caller sink's backpressure sleep. Sleeping samples do not establish CPU
  consumption or measured wakeup frequency.
- The audio callback had 57 of 7,954 observations inside its work path, including
  Rodio and CoreAudio conversion. A CoreAudio resampler stack was present, but
  actual negotiated device format and exact resampling cost were not measured.
  No device setting was changed.
- Spectrum-on versus spectrum-off background playback differed by about one
  percentage point. Source review confirms analysis continues while hidden. The
  caller also retains periodic UI/control work while idle. These are separate
  caller candidates requiring their own measured changes.

The caller supplies its own sink. Optimizing librespot's built-in Rodio queue
would not affect this integration. No queue size, buffer policy, polling interval,
mixing precision, playback quality, normalization or media-control behavior was
changed. Allocation and locking costs were not measured precisely enough to
justify speculative changes. `sample` worked with the existing permissions;
Instruments discovery failed on a sandbox cache-write restriction and was not
needed for the completed captures. No system security settings were changed.

## Decoder experiment

The [numeric results](performance-macos-vorbis-results.json) preserve every paired
observation and the repeated live windows without private track or process data.

See [the standalone reproducer](../contrib/decoder-bench/README.md). It calls the
actual `SymphoniaDecoder`, retaining packet allocation and f64 conversion. The
candidate enables only Symphonia's optional `opt-simd` feature. The initial
baseline used the published crate and the candidate used this fork's sources;
all 100 Rust source files across the six involved librespot packages matched.
Common dependency versions were identical. The retained reproducer uses the
local fork for both variants and keeps SIMD opt-in inside its own workspace.

The original generated fixture is 16 seconds of stereo 44.1 kHz chords,
transients and silence, encoded with FFmpeg 8.1.1's native Vorbis encoder at a
requested 160 kbps (151,121 bits/s including container overhead). No commercial
or user audio was copied. Encoded input is loaded before timing; two decodes
warm each process. Each observation decodes 200 passes, or 3,200 seconds of media.
The measured interval includes decoder construction and all normal packet
allocations. It excludes network, audio output, UI, spectrum and sample checking.

`CLOCK_PROCESS_CPUTIME_ID` measures process CPU. Real-time-equivalent CPU is
`100 * CPU seconds / decoded media seconds`; it is not the instantaneous CPU
usage of the faster-than-real-time benchmark.

| Pair | Order | Scalar CPU s | SIMD CPU s | Scalar wall s | SIMD wall s |
|---|---|---:|---:|---:|---:|
| 1 | scalar → SIMD | 2.415978 | 2.115576 | 2.421300 | 2.120802 |
| 2 | SIMD → scalar | 2.421522 | 2.129893 | 2.427441 | 2.135004 |
| 3 | scalar → SIMD | 2.430886 | 2.122982 | 2.436668 | 2.127995 |
| 4 | SIMD → scalar | 2.418262 | 2.109973 | 2.423864 | 2.114865 |
| 5 | scalar → SIMD | 2.412948 | 2.109569 | 2.418609 | 2.114637 |

Median real-time-equivalent CPU was **0.075570687% scalar** and
**0.066111750% SIMD**. The respective ranges were 0.075404625–0.075965188% and
0.065924031–0.066559156%. This is a repeatable isolated improvement, with no
measured improvement to the installed application's CPU.

## Correctness, costs and remaining limits

The minimal checks cover two distinct risks: complete decoding and seek/reset
after EOF. Full decoding yielded 1,411,200 samples; seeking to 5,731 ms returned
5,712 ms in both variants and yielded 905,344 remaining samples. Positions,
packet lengths and skipped markers matched exactly; every sample was finite.
Maximum absolute sample difference was `8.9407e-8`, and RMS difference was about
`1.05e-8`, below the predeclared limits of `1e-5` maximum and `1e-6` RMS. Outputs
are not bit-identical. This is numerical decoding validation, not listening or
acoustic latency measurement.

The fixture has 690 long 1,024-frame packets and a 64-frame tail. It does not
exercise Vorbis short/long block transitions; a suitable encoder was unavailable.
It is not representative of all music or a codec conformance suite. Other
architectures were not benchmarked. RustFFT selects supported SIMD at runtime;
unsupported targets switch to its scalar implementation, so enabling the feature
globally would also change their transform backend without measured evidence.

SIMD adds RustFFT 6.4.1, num-complex 0.4.6, primal-check 0.3.4,
strength_reduce 0.2.4 and transpose 0.2.3. The isolated executable grew from
1,311,232 to 1,772,160 bytes. That is not an installed-app size estimate.
Symphonia retains its MPL-2.0 license; RustFFT is MIT OR Apache-2.0. Their source
and license notices are unmodified.

The default feature change was rejected. No integrated app speedup, acoustic
pause latency, native media-control latency, sustained dropout resistance or
Linux improvement is claimed. Existing queue correctness remains untouched. The
next useful work is a separately approved caller investigation of presentation,
hidden spectrum processing and idle timers, followed by an isolated signed app
comparison before any production integration.

## Reproducer validation

Both release variants rebuilt successfully from the retained standalone layout.
Their resolved package versions and features matched the measured variants, so
the table above was not replaced with a new workload. Full/seek checks passed
again with the same maximum sample difference. `cargo fmt --check`, Python syntax
checks, and `cargo clippy --locked --offline --all-targets --all-features -- -D warnings`
passed for the standalone project. Root formatting and `git diff --check` passed.
The root production manifests and lockfile are byte-for-byte unchanged.
