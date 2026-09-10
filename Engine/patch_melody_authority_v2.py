#!/usr/bin/env python3
"""Patch FORGE's note-target brain so a confident reference can rescue real missed notes.

The old implementation only trusted a reference note when it was within ~1.45 semitones
of the raw singer. That made a badly missed note impossible to repair. This patch keeps
reference authority confidence-gated, octave-safe and rough-vocal-safe, but permits a
stable reference event to correct several semitones when the evidence is strong.
"""
from pathlib import Path
import re

ENGINE = Path(__file__).with_name("forge_engine.py")
src = ENGINE.read_text(encoding="utf-8")

replacement = r'''def _forge_weighted_reference_note(ref_t, ref_midi, ref_voiced, ref_prob, r0, r1, raw_center):
    """Return (target_midi, quality, concentration, spread, support) or None.

    A reference note earns authority only when the F0 tracker is voiced, confident and
    concentrated around one semitone. Octave choice is anchored to the singer so an
    octave-tracking error does not throw a vocal by 12 semitones.
    """
    lo=min(float(r0),float(r1))-.065; hi=max(float(r0),float(r1))+.065
    mask=(ref_t>=lo)&(ref_t<=hi)&np.isfinite(ref_midi)&ref_voiced&np.isfinite(ref_prob)&(ref_prob>.40)
    if int(mask.sum())<4:
        return None
    vals=np.asarray(ref_midi[mask],dtype=float); weights=np.clip(np.asarray(ref_prob[mask],dtype=float),.05,1.0)
    rounded=np.rint(vals).astype(int)
    candidates=range(int(np.floor(np.percentile(vals,10)))-1,int(np.ceil(np.percentile(vals,90)))+2)
    sigma=.34
    scores={int(n):float(np.sum(weights*np.exp(-.5*((vals-float(n))/sigma)**2))) for n in candidates}
    if not scores:
        return None
    modal=max(scores,key=scores.get)
    total=float(np.sum(weights))+1e-12
    concentration=float(np.sum(weights[np.abs(vals-modal)<=.48])/total)
    spread=float(np.percentile(vals,80)-np.percentile(vals,20)) if len(vals)>=5 else float(np.ptp(vals))
    med_prob=float(np.median(weights))
    support=float(np.clip(len(vals)/8.0,0,1))
    stability=float(np.clip(1.0-spread/1.35,0,1))
    quality=float(np.clip((.43*med_prob+.36*concentration+.21*stability)*(.72+.28*support),0,1))

    # Preserve the singer's intended register while retaining the reference pitch class.
    octave_candidates=[modal-24,modal-12,modal,modal+12,modal+24]
    target=min(octave_candidates,key=lambda n:abs(float(n)-float(raw_center)))
    return int(target),quality,concentration,spread,int(len(vals))


def build_targets(raw,sr,reference=None,genre="modern_metalcore"):
    t,midi,voiced,prob=pyin_track(raw,sr,512)
    events=segment_notes(t,midi,voiced,prob)
    key_src=reference if reference is not None else raw
    root,mode,pcs,key_conf=detect_key(key_src,sr,genre)
    ref_t=ref_midi=ref_voiced=ref_prob=mapped=None
    if reference is not None and len(reference)>sr:
        try:
            ref_t,ref_midi,ref_voiced,ref_prob=pyin_track(reference,sr,512)
            mapped=reference_map(raw,reference,sr,t)
        except Exception:
            mapped=None

    rows=[]
    for eid,(a,b) in enumerate(events):
        inds=np.arange(a,b+1); vals=midi[inds]; good=np.isfinite(vals)
        if good.sum()<3:
            continue
        center=float(np.nanmedian(vals[good]))
        finite_prob=prob[inds][np.isfinite(prob[inds])]
        med_prob=float(np.nanmedian(finite_prob)) if finite_prob.size else 0.0
        flat,zcr=spectral_event_features(raw,sr,float(t[a]),float(t[b]))
        rough_score=float(np.clip((.58-med_prob)*2.0+max(0,flat-.12)*2.2+max(0,zcr-.20)*1.4,0,1))
        protected=bool((med_prob<.50 and flat>.10) or rough_score>.58)
        target=None
        authority="protected" if protected else "scale"
        ref_conf=0.0; ref_concentration=0.0; ref_spread=99.0; ref_support=0; ref_distance=0.0

        if not protected and mapped is not None:
            estimate=_forge_weighted_reference_note(ref_t,ref_midi,ref_voiced,ref_prob,mapped[a],mapped[b],center)
            if estimate is not None:
                rn,ref_conf,ref_concentration,ref_spread,ref_support=estimate
                ref_distance=abs(float(rn)-center)
                # Normal, close reference notes need moderate evidence. True rescue notes
                # (2-5.5 semitones away) require substantially stronger evidence.
                close_ok=(ref_distance<=1.80 and ref_conf>=.61 and ref_concentration>=.52)
                rescue_ok=(ref_distance<=5.50 and ref_conf>=.69 and ref_concentration>=.60 and ref_spread<=1.05 and ref_support>=4)
                extreme_ok=(ref_distance<=7.00 and ref_conf>=.84 and ref_concentration>=.74 and ref_spread<=.72 and ref_support>=6)
                if close_ok or rescue_ok or extreme_ok:
                    target=int(rn)
                    authority="reference_rescue" if ref_distance>1.80 else "reference"

        if target is None and not protected:
            target=choose_scale_note(center,pcs)
        if target is None:
            target=int(round(center))

        rows.append(dict(event=eid,start_s=float(t[a]),end_s=float(t[b]),raw_center=center,
                         target_midi=int(target),authority=authority,reference_confidence=float(ref_conf),
                         reference_concentration=float(ref_concentration),reference_spread=float(ref_spread),
                         reference_support=int(ref_support),reference_distance_semitones=float(ref_distance),
                         pitch_confidence=med_prob,spectral_flatness=flat,rough_score=rough_score,
                         protected_unpitched=protected))
    return pd.DataFrame(rows),(root,mode,pcs,key_conf)
'''

pattern = r'def build_targets\(raw,sr,reference=None,genre="modern_metalcore"\):.*?(?=\n\ndef psola_natural_tune)'
new_src, count = re.subn(pattern, replacement.rstrip(), src, count=1, flags=re.S)
if count != 1:
    raise SystemExit(f"Could not patch build_targets exactly once (matches={count})")
ENGINE.write_text(new_src, encoding="utf-8")
print("FORGE Melody Authority v2 patch applied")
