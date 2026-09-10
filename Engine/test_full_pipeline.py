#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math, os, subprocess, sys, tempfile
from pathlib import Path
import numpy as np
import soundfile as sf
import librosa

SR = 44100
NOTE_HZ = lambda m: 440.0 * (2.0 ** ((m - 69.0) / 12.0))


def tone(midi, dur, cents=0.0, amp=0.18, vibrato_cents=10.0, rough=0.0, seed=0):
    n = int(SR * dur)
    t = np.arange(n) / SR
    vib = vibrato_cents * np.sin(2*np.pi*5.2*t) / 100.0
    inst = NOTE_HZ(midi + cents/100.0 + vib)
    phase = 2*np.pi*np.cumsum(inst) / SR
    y = amp*(np.sin(phase) + 0.18*np.sin(2*phase) + 0.08*np.sin(3*phase))
    if rough > 0:
        rng = np.random.default_rng(seed)
        y += rough * rng.standard_normal(n)
        y = np.tanh(y * 2.2) / 2.2
    f = min(int(0.018*SR), n//4)
    if f > 4:
        r = np.linspace(0,1,f)
        y[:f] *= r; y[-f:] *= r[::-1]
    return y.astype(np.float64)


def silence(dur): return np.zeros(int(SR*dur), np.float64)


def make_test_audio(root: Path):
    # A minor / metalcore-style phrase. Raw take is intentionally sharp/flat and includes one rough note.
    notes = [57,60,64,67,69,67,64,62,60,64,57]
    cents = [31,-26,24,-33,37,-21,28,-29,22,-24,35]
    raw_parts=[]; ref_parts=[]
    for i,(m,c) in enumerate(zip(notes,cents)):
        raw_parts += [tone(m,0.55,cents=c,vibrato_cents=14,rough=(0.09 if i==5 else 0),seed=80+i), silence(0.11)]
        ref_parts += [tone(m,0.55,cents=0,vibrato_cents=5,amp=0.16), silence(0.11)]
    raw=np.concatenate(raw_parts)
    lead_ref=np.concatenate(ref_parts)
    # Reinforce A minor key in the stereo reference with quiet A/C/E/G backing tones.
    t=np.arange(len(lead_ref))/SR
    backing=np.zeros_like(lead_ref)
    for m,a in [(45,.018),(48,.013),(52,.014),(55,.009)]: backing += a*np.sin(2*np.pi*NOTE_HZ(m)*t)
    left=lead_ref+backing
    right=lead_ref+0.97*backing
    raw_path=root/'raw.wav'; ref_path=root/'reference.wav'
    sf.write(raw_path, raw, SR, subtype='PCM_24')
    sf.write(ref_path, np.column_stack([left,right]), SR, subtype='PCM_24')
    return raw_path, ref_path


def engine_cmd(engine: Path, args):
    cmd = ([sys.executable, str(engine)] if engine.suffix.lower()=='.py' else [str(engine)]) + list(args)
    p=subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=300)
    print('>',' '.join(cmd[:2] + list(args[:2])))
    print(p.stdout[-2500:])
    if p.returncode != 0: raise RuntimeError(f'Engine command failed ({p.returncode}): {p.stdout[-1200:]}')
    return p.stdout


def load_mono(path):
    y,sr=sf.read(path,dtype='float64',always_2d=True)
    return y.mean(axis=1),sr


def rms_db(y): return 20*math.log10(float(np.sqrt(np.mean(y*y)))+1e-12)


def pitch_qc(dry_path: Path, report):
    y,sr=load_mono(dry_path)
    f0,voiced,prob=librosa.pyin(y.astype(float), fmin=librosa.note_to_hz('A2'), fmax=librosa.note_to_hz('C6'), sr=sr, frame_length=2048, hop_length=512)
    tt=librosa.frames_to_time(np.arange(len(f0)),sr=sr,hop_length=512)
    midi=librosa.hz_to_midi(f0)
    errs=[]
    for e in report['events']:
        if e.get('protected_unpitched'): continue
        mask=(tt>=e['start_s']+.06)&(tt<=e['end_s']-.05)&voiced&np.isfinite(midi)
        if np.sum(mask)>=2:
            errs.append(abs(float(np.median(midi[mask]))-float(e['target_midi']))*100.0)
    if len(errs)<5: raise RuntimeError(f'Pitch QC had too few measurable notes: {len(errs)}')
    med=float(np.median(errs)); p90=float(np.percentile(errs,90))
    print(f'PITCH_QC median={med:.2f}c p90={p90:.2f}c n={len(errs)}')
    if med > 18.0 or p90 > 45.0: raise RuntimeError(f'Perfect Lead pitch QC failed: median {med:.1f}c p90 {p90:.1f}c')
    return med,p90


def assert_audio(path: Path, allow_stereo=True):
    if not path.exists() or path.stat().st_size < 2048: raise RuntimeError(f'Missing/empty output: {path.name}')
    x,sr=sf.read(path,dtype='float64',always_2d=True)
    if sr != SR: raise RuntimeError(f'Wrong sample rate for {path.name}: {sr}')
    if not np.all(np.isfinite(x)): raise RuntimeError(f'NaN/Inf in {path.name}')
    peak=float(np.max(np.abs(x)))
    if peak > 1.001: raise RuntimeError(f'Clipping in {path.name}: {peak}')
    if float(np.sqrt(np.mean(x*x))) < 1e-5: raise RuntimeError(f'Output is effectively silent: {path.name}')
    return x


def correlation(a,b):
    n=min(len(a),len(b)); a=a[:n]; b=b[:n]
    mask=(np.abs(a)+np.abs(b))>2e-4
    if np.sum(mask)<100: return 1.0
    return float(np.corrcoef(a[mask],b[mask])[0,1])


def run_full(engine: Path):
    with tempfile.TemporaryDirectory(prefix='forge-functional-') as td:
        root=Path(td); raw,ref=make_test_audio(root)
        dry=root/'perfect_lead_dry.wav'; mixed=root/'mixed_lead.wav'; stack=root/'stack'
        engine_cmd(engine,['perfect-lead','--input',str(raw),'--reference',str(ref),'--output',str(dry),'--mixed-output',str(mixed),'--genre','modern_metalcore','--accuracy','0.88','--expression','0.69','--repair','0.66','--timing-tightness','0.72','--humanize','0.68','--mix-strength','0.84'])
        report=json.loads(dry.with_suffix('.json').read_text())
        key=report['key']['name']
        print('KEY_QC',key,'confidence',report['key']['confidence'],'protected',report.get('protected_rough_events'))
        if not key.startswith('A ') or 'Minor' not in key: raise RuntimeError(f'Auto-key regression: expected A minor family, got {key}')
        dry_x=assert_audio(dry)[:,0]; mixed_x=assert_audio(mixed)[:,0]
        pitch_qc(dry,report)
        if rms_db(mixed_x) < rms_db(dry_x)+0.5: raise RuntimeError(f'Mix Assist failed loudness/density gate: dry {rms_db(dry_x):.2f}, mixed {rms_db(mixed_x):.2f}')
        engine_cmd(engine,['build-stack','--input',str(dry),'--reference',str(ref),'--output-dir',str(stack),'--genre','modern_metalcore','--stack-size','0.82','--width','0.86','--tightness','0.76','--harmony-intensity','0.82','--octave-blend','0.58','--character','0.68'])
        expected=['01_MASTER_LEAD_DRY.wav','02_MASTER_LEAD_MIXED.wav','03_DOUBLE_L.wav','04_DOUBLE_R.wav','05_UPPER_HARMONY.wav','06_LOWER_HARMONY.wav','07_HIGH_OCTAVE.wav','08_LOW_OCTAVE.wav','09_STACK_REFERENCE_MIX.wav']
        audio={n:assert_audio(stack/n) for n in expected}
        lead=audio['01_MASTER_LEAD_DRY.wav'][:,0]
        dl=audio['03_DOUBLE_L.wav'][:,0]; dr=audio['04_DOUBLE_R.wav'][:,0]
        up=audio['05_UPPER_HARMONY.wav'][:,0]; low=audio['06_LOWER_HARMONY.wav'][:,0]
        if abs(correlation(dl,dr)) > .9995: raise RuntimeError('Double L/R are effectively identical')
        if abs(correlation(lead,up)) > .995: raise RuntimeError('Upper harmony is too similar to lead')
        if abs(correlation(lead,low)) > .995: raise RuntimeError('Lower harmony is too similar to lead')
        if audio['09_STACK_REFERENCE_MIX.wav'].shape[1] != 2: raise RuntimeError('Stack reference mix is not stereo')
        # Smoke every genre profile through the exact CLI used by the VST.
        for genre in ['post_hardcore','alt_metal','pop_punk']:
            d=root/f'{genre}_dry.wav'; m=root/f'{genre}_mix.wav'
            engine_cmd(engine,['perfect-lead','--input',str(raw),'--reference',str(ref),'--output',str(d),'--mixed-output',str(m),'--genre',genre])
            assert_audio(d); assert_audio(m)
        print('FORGE_FULL_FUNCTIONAL_TEST=PASS')
        print('CHECKED=auto-key+perfect-lead+mix-assist+rough-aware-analysis+doubles+harmonies+octaves+stereo-stack+all-genres')


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--engine',required=True); args=ap.parse_args()
    engine=Path(args.engine).resolve()
    if not engine.exists(): raise SystemExit(f'Engine not found: {engine}')
    run_full(engine)

if __name__=='__main__': main()
