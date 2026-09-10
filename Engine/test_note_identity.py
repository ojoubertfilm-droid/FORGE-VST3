#!/usr/bin/env python3
"""FORGE missed-note regression.

This is intentionally harder than the normal centering test. The raw singer performs
several notes 2-4 semitones away from the reference. FORGE must choose the reference
melody when reference evidence is strong, then audibly move those notes toward the
intended targets. This protects the core product promise: the singer does not have to
already hit every note for Perfect Lead to work.
"""
from __future__ import annotations
import argparse, json, math, subprocess, tempfile
from pathlib import Path
import numpy as np
import soundfile as sf
import librosa

SR=44100
EXPECTED=[57,60,64,67,69,67,65,64,62,59,60,57]  # A natural minor melody
RAW_NOTES=[57,62,64,63,69,67,66,64,62,61,60,57]
MISSED={1,3,9}
DUR=.46
GAP=.085


def note_wave(midi, dur, amp, cents=0.0, vibrato_cents=7.0):
    n=int(SR*dur); t=np.arange(n,dtype=float)/SR
    base=440.0*2**(((midi+cents/100.0)-69.0)/12.0)
    vib=(vibrato_cents/1200.0)*np.sin(2*np.pi*5.15*t+0.31)
    phase=2*np.pi*np.cumsum(base*(2**vib))/SR
    # Vocal-like harmonic source; enough harmonic structure for pYIN without being a sterile sine.
    y=np.sin(phase)+.29*np.sin(2*phase+.2)+.12*np.sin(3*phase+.55)
    env=np.ones(n); f=min(int(.035*SR),n//4)
    if f>2:
        ramp=np.sin(np.linspace(0,np.pi/2,f))**2; env[:f]=ramp; env[-f:]=ramp[::-1]
    return (amp*y*env/1.41).astype(np.float64)


def make_fixture(root: Path):
    rng=np.random.default_rng(118)
    raw=[]; ref=[]; centers=[]; starts=[]
    cursor=0.0
    for i,(want,got) in enumerate(zip(EXPECTED,RAW_NOTES)):
        amp=.14+.018*(i%5)
        starts.append(cursor); centers.append(cursor+DUR*.53)
        ref.append(note_wave(want,DUR,amp,cents=(i%3-1)*2.0,vibrato_cents=5.0))
        raw.append(note_wave(got,DUR,amp*.96,cents=(i%4-1.5)*7.0,vibrato_cents=10.0))
        gap=np.zeros(int(SR*GAP),dtype=float)
        ref.append(gap.copy()); raw.append(gap.copy())
        cursor+=DUR+GAP
    raw=np.concatenate(raw); ref=np.concatenate(ref)
    raw+=rng.normal(0,0.00035,size=len(raw))
    ref+=rng.normal(0,0.00018,size=len(ref))
    raw_path=root/'raw_missed.wav'; ref_path=root/'reference_correct.wav'
    sf.write(raw_path,raw,SR,subtype='PCM_24'); sf.write(ref_path,ref,SR,subtype='PCM_24')
    return raw_path,ref_path,centers,starts,raw


def event_for_time(events,t):
    containing=[e for e in events if float(e['start_s'])-.035<=t<=float(e['end_s'])+.035]
    if containing:
        return min(containing,key=lambda e:abs((float(e['start_s'])+float(e['end_s']))*.5-t))
    return min(events,key=lambda e:abs((float(e['start_s'])+float(e['end_s']))*.5-t))


def median_midi(y,start):
    a=int((start+DUR*.28)*SR); b=int((start+DUR*.78)*SR); seg=np.asarray(y[a:b],dtype=float)
    f0,voiced,prob=librosa.pyin(seg,fmin=librosa.note_to_hz('A2'),fmax=librosa.note_to_hz('C6'),sr=SR,frame_length=2048,hop_length=256)
    m=librosa.hz_to_midi(f0); mask=np.isfinite(m)&voiced&(prob>.35)
    return float(np.median(m[mask])) if int(mask.sum())>=3 else float('nan')


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--engine',required=True); args=ap.parse_args()
    engine=str(Path(args.engine).resolve())
    with tempfile.TemporaryDirectory(prefix='forge-note-identity-') as td:
        root=Path(td); raw_path,ref_path,centers,starts,raw=make_fixture(root)
        dry=root/'perfect.wav'; mixed=root/'mixed_lead.wav'
        cmd=[engine,'perfect-lead','--input',str(raw_path),'--reference',str(ref_path),'--output',str(dry),'--mixed-output',str(mixed),'--genre','modern_metalcore','--accuracy','.96','--expression','.66','--repair','.95','--timing-tightness','.74','--humanize','.64','--mix-strength','.80']
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=180)
        print(p.stdout,end=''); print(p.stderr,end='')
        if p.returncode!=0: raise SystemExit(f'Perfect Lead failed: {p.returncode}')
        report=json.loads(dry.with_suffix('.json').read_text())
        events=report.get('events') or []
        if len(events)<len(EXPECTED)-2: raise SystemExit(f'Too few note events: {len(events)}')

        exact=0; missed_exact=0; rescue_authority=0; rows=[]
        for i,(want,got,center) in enumerate(zip(EXPECTED,RAW_NOTES,centers)):
            e=event_for_time(events,center); target=int(e['target_midi']); ok=(target==want)
            exact+=int(ok)
            if i in MISSED:
                missed_exact+=int(ok)
                rescue_authority+=int(str(e.get('authority','')).startswith('reference'))
            rows.append((i,want,got,target,e.get('authority'),float(e.get('reference_confidence',0))))
        for r in rows: print('TARGET_CHECK',r)
        exact_rate=exact/len(EXPECTED)
        if exact_rate<.83: raise SystemExit(f'Intended target accuracy too low: {exact_rate:.3f}')
        if missed_exact<len(MISSED): raise SystemExit(f'Missed-note target recovery failed: {missed_exact}/{len(MISSED)}')
        if rescue_authority<len(MISSED): raise SystemExit(f'Reference authority did not own all deliberate misses: {rescue_authority}/{len(MISSED)}')

        out,_=sf.read(dry,dtype='float64',always_2d=False)
        if np.ndim(out)>1: out=np.mean(out[:,:2],axis=1)
        rendered_pass=0
        for i in sorted(MISSED):
            before=abs(float(RAW_NOTES[i])-float(EXPECTED[i]))
            after_m=median_midi(out,starts[i])
            if not math.isfinite(after_m): raise SystemExit(f'No rendered F0 for missed event {i}')
            after=abs(after_m-float(EXPECTED[i]))
            improvement=before-after
            print(f'RENDER_CHECK event={i} before_err={before:.3f}st after_err={after:.3f}st improvement={improvement:.3f}st')
            if after<=.55 and improvement>=1.20: rendered_pass+=1
        if rendered_pass<len(MISSED): raise SystemExit(f'Rendered missed-note recovery failed: {rendered_pass}/{len(MISSED)}')

        if not np.all(np.isfinite(out)) or np.max(np.abs(out))>1.001: raise SystemExit('Perfect Lead output invalid/clipping')
        print(f'FORGE_NOTE_IDENTITY=PASS|TARGET_EXACT={exact_rate:.3f}|MISSED_RECOVERED={missed_exact}/{len(MISSED)}|RENDERED={rendered_pass}/{len(MISSED)}')

if __name__=='__main__': main()
