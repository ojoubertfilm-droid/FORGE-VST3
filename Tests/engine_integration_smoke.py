#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math, subprocess, sys, tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
import librosa

SR = 44100


def tone(freq: float, dur: float, cents: float = 0.0, vib_cents: float = 0.0, amp: float = 0.18):
    n = int(SR * dur)
    t = np.arange(n, dtype=np.float64) / SR
    f = freq * (2.0 ** (cents / 1200.0))
    if vib_cents:
        inst = f * (2.0 ** ((vib_cents * np.sin(2 * np.pi * 5.1 * t)) / 1200.0))
        phase = 2 * np.pi * np.cumsum(inst) / SR
        y = amp * np.sin(phase)
    else:
        y = amp * np.sin(2 * np.pi * f * t)
    fade = min(int(0.025 * SR), n // 4)
    if fade > 2:
        r = np.linspace(0, 1, fade)
        y[:fade] *= r
        y[-fade:] *= r[::-1]
    return y


def make_fixture(root: Path):
    # A-minor biased phrase. Raw is intentionally off-center and humanized.
    exact = [220.000, 261.626, 329.628, 440.000, 391.995, 329.628, 293.665, 261.626, 220.000]
    detune = [42, -31, 57, 35, -38, 49, -44, 32, 46]
    raw_parts, ref_parts = [], []
    gap = np.zeros(int(0.075 * SR), dtype=np.float64)
    for i, f in enumerate(exact):
        raw_parts += [tone(f, 0.56, detune[i], 11.0, 0.17), gap]
        ref_parts += [tone(f, 0.56, 0.0, 4.0, 0.18), gap]
    raw = np.concatenate(raw_parts)
    ref = np.concatenate(ref_parts)
    # Stereo reference exercises the centered-reference proxy path.
    ref_st = np.column_stack([ref, ref * 0.985])
    root.mkdir(parents=True, exist_ok=True)
    sf.write(root / "raw.wav", raw, SR, subtype="PCM_24")
    sf.write(root / "reference.wav", ref_st, SR, subtype="PCM_24")


def run(cmd, *args):
    full = list(cmd) + [str(x) for x in args]
    p = subprocess.run(full, capture_output=True, text=True, timeout=240)
    print("$", " ".join(full))
    if p.stdout:
        print(p.stdout.strip())
    if p.stderr:
        print(p.stderr.strip(), file=sys.stderr)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed ({p.returncode}): {' '.join(full)}")
    return p.stdout + p.stderr


def read_audio(path: Path):
    if not path.exists() or path.stat().st_size < 4096:
        raise AssertionError(f"Missing/empty output: {path}")
    y, sr = sf.read(path, dtype="float64", always_2d=True)
    if sr != SR:
        raise AssertionError(f"Unexpected sample rate for {path}: {sr}")
    if not np.isfinite(y).all():
        raise AssertionError(f"NaN/Inf in {path}")
    peak = float(np.max(np.abs(y)))
    rms = float(np.sqrt(np.mean(y * y) + 1e-18))
    if peak > 1.001:
        raise AssertionError(f"Clipping in {path}: {peak}")
    if rms < 1e-6:
        raise AssertionError(f"Silent output: {path}")
    return y, peak, rms


def pitch_qc(dry_path: Path):
    sidecar = dry_path.with_suffix(".json")
    report = json.loads(sidecar.read_text())
    events = [e for e in report.get("events", []) if not e.get("protected_unpitched", False)]
    if len(events) < 5:
        raise AssertionError(f"Too few pitched events: {len(events)}")
    y, sr = sf.read(dry_path, dtype="float64")
    if y.ndim > 1:
        y = np.mean(y[:, :2], axis=1)
    f0, voiced, prob = librosa.pyin(y.astype(float), fmin=librosa.note_to_hz("A2"), fmax=librosa.note_to_hz("C6"), sr=sr, frame_length=2048, hop_length=256)
    tt = librosa.frames_to_time(np.arange(len(f0)), sr=sr, hop_length=256)
    midi = librosa.hz_to_midi(f0)
    errs = []
    for e in events:
        m = (tt >= float(e["start_s"]) + 0.08) & (tt <= float(e["end_s"]) - 0.06) & np.isfinite(midi) & voiced
        if np.sum(m) >= 3:
            center = float(np.nanmedian(midi[m]))
            errs.append(abs(center - float(e["target_midi"])) * 100.0)
    if len(errs) < 4:
        raise AssertionError("Could not measure enough tuned events")
    med = float(np.median(errs)); p90 = float(np.percentile(errs, 90))
    print(f"PITCH_QC median={med:.2f}c p90={p90:.2f}c events={len(errs)}")
    if p90 > 35.0:
        raise AssertionError(f"Tuning P90 too loose for install candidate: {p90:.2f} cents")
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", nargs="+", required=True, help="Engine command, e.g. python Engine/forge_engine.py OR path/to/forge_engine.exe")
    ap.add_argument("--work", required=True)
    args = ap.parse_args()
    work = Path(args.work).resolve()
    make_fixture(work)
    cmd = args.engine
    raw, ref = work / "raw.wav", work / "reference.wav"

    base = work / "base"
    base.mkdir(exist_ok=True)
    dry, mixed = base / "perfect_lead_dry.wav", base / "mixed_lead.wav"
    log = run(cmd, "perfect-lead", "--input", raw, "--reference", ref, "--output", dry, "--mixed-output", mixed,
              "--genre", "modern_metalcore", "--accuracy", "0.90", "--expression", "0.68", "--repair", "0.72",
              "--timing-tightness", "0.72", "--humanize", "0.68", "--mix-strength", "0.84")
    if "FORGE_KEY=" not in log:
        raise AssertionError("Perfect Lead did not report a detected key")
    dry_y, _, _ = read_audio(dry)
    mixed_y, _, _ = read_audio(mixed)
    if np.sqrt(np.mean((dry_y - mixed_y) ** 2)) < 1e-5:
        raise AssertionError("Mix Assist produced no meaningful change")
    report = pitch_qc(dry)

    # Prove the lead controls are not decorative: a deliberately loose profile must render differently.
    alt = work / "alt"
    alt.mkdir(exist_ok=True)
    alt_dry, alt_mixed = alt / "perfect_lead_dry.wav", alt / "mixed_lead.wav"
    run(cmd, "perfect-lead", "--input", raw, "--reference", ref, "--output", alt_dry, "--mixed-output", alt_mixed,
        "--genre", "post_hardcore", "--accuracy", "0.35", "--expression", "0.94", "--repair", "0.25",
        "--timing-tightness", "0.25", "--humanize", "0.95", "--mix-strength", "0.30")
    alt_y, _, _ = read_audio(alt_dry)
    if np.sqrt(np.mean((dry_y - alt_y) ** 2)) < 2e-5:
        raise AssertionError("Lead control profile did not change rendered audio")

    stack = work / "stack"
    slog = run(cmd, "build-stack", "--input", dry, "--reference", ref, "--output-dir", stack,
               "--genre", "modern_metalcore", "--stack-size", "0.86", "--width", "0.88", "--tightness", "0.78",
               "--harmony-intensity", "0.82", "--octave-blend", "0.58", "--character", "0.72")
    if "STACK_KEY=" not in slog:
        raise AssertionError("Stack stage did not report its harmonic key")
    expected = [
        "01_MASTER_LEAD_DRY.wav", "02_MASTER_LEAD_MIXED.wav", "03_DOUBLE_L.wav", "04_DOUBLE_R.wav",
        "05_UPPER_HARMONY.wav", "06_LOWER_HARMONY.wav", "07_HIGH_OCTAVE.wav", "08_LOW_OCTAVE.wav",
        "09_STACK_REFERENCE_MIX.wav"
    ]
    stats = {}
    for name in expected:
        y, peak, rms = read_audio(stack / name)
        stats[name] = {"peak": peak, "rms": rms, "channels": int(y.shape[1])}
    if stats["09_STACK_REFERENCE_MIX.wav"]["channels"] != 2:
        raise AssertionError("Stack reference mix is not stereo")

    # Prove stack controls alter the output.
    stack_alt = work / "stack_alt"
    run(cmd, "build-stack", "--input", dry, "--reference", ref, "--output-dir", stack_alt,
        "--genre", "post_hardcore", "--stack-size", "0.30", "--width", "0.20", "--tightness", "0.25",
        "--harmony-intensity", "0.25", "--octave-blend", "0.15", "--character", "0.20")
    a, _, _ = read_audio(stack / "09_STACK_REFERENCE_MIX.wav")
    b, _, _ = read_audio(stack_alt / "09_STACK_REFERENCE_MIX.wav")
    if np.sqrt(np.mean((a - b) ** 2)) < 1e-5:
        raise AssertionError("Stack control profile did not change rendered stack")

    print("FORGE_FULL_INTEGRATION=PASS")
    print(f"KEY={report['key']['name']}|EVENTS={len(report.get('events', []))}|OUTPUTS={len(expected)}")


if __name__ == "__main__":
    main()
