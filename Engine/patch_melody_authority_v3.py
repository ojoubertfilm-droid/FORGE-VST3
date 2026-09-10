#!/usr/bin/env python3
"""FORGE Melody Authority v3.

Fix a fundamental failure mode in reference-guided vocal correction: a singer who
misses a note must not cause the alignment itself to jump to a different reference
note merely because that wrong pitch has a lower chroma-DTW cost.

v3 makes temporal/phrase correspondence the primary authority. Chroma DTW is kept as
an optional local refinement only when it agrees with the time anchor. Reference pitch
then determines the intended note, with confidence, rough-vocal and register guards.
"""
from pathlib import Path
import re

ENGINE = Path(__file__).with_name("forge_engine.py")
src = ENGINE.read_text(encoding="utf-8")

replacement = r'''def _forge_weighted_reference_note(ref_t, ref_midi, ref_voiced, ref_prob, r0, r1, raw_center):
    """Estimate a stable reference note in a known time window.

    Returns (target_midi, quality, concentration, spread, support) or None. Pitch class
    comes from the reference, but octave is anchored to the singer's register so an F0
    octave error cannot move a vocal by 12 semitones.
    """
    lo=min(float(r0),float(r1)); hi=max(float(r0),float(r1))
    # Read mostly the body of the note; modest padding helps short events without
    # allowing the neighbouring phrase to dominate.
    dur=max(hi-lo,.025)
    core_lo=lo+.10*dur-.025
    core_hi=hi-.10*dur+.025
    mask=(ref_t>=core_lo)&(ref_t<=core_hi)&np.isfinite(ref_midi)&ref_voiced&np.isfinite(ref_prob)&(ref_prob>.38)
    if int(mask.sum())<3:
        return None
    vals=np.asarray(ref_midi[mask],dtype=float)
    weights=np.clip(np.asarray(ref_prob[mask],dtype=float),.05,1.0)
    candidates=range(int(np.floor(np.percentile(vals,8)))-1,int(np.ceil(np.percentile(vals,92)))+2)
    sigma=.32
    scores={int(n):float(np.sum(weights*np.exp(-.5*((vals-float(n))/sigma)**2))) for n in candidates}
    if not scores:
        return None
    modal=max(scores,key=scores.get)
    total=float(np.sum(weights))+1e-12
    concentration=float(np.sum(weights[np.abs(vals-modal)<=.46])/total)
    spread=float(np.percentile(vals,80)-np.percentile(vals,20)) if len(vals)>=5 else float(np.ptp(vals))
    med_prob=float(np.median(weights))
    support=float(np.clip(len(vals)/7.0,0,1))
    stability=float(np.clip(1.0-spread/1.25,0,1))
    quality=float(np.clip((.44*med_prob+.37*concentration+.19*stability)*(.70+.30*support),0,1))

    octave_candidates=[modal-24,modal-12,modal,modal+12,modal+24]
    target=min(octave_candidates,key=lambda n:abs(float(n)-float(raw_center)))
    return int(target),quality,concentration,spread,int(len(vals))


def _forge_temporal_reference_window(raw_t, a, b, ref_t, mapped=None):
    """Map one raw note to reference time without letting a wrong pitch steer alignment.

    Absolute/relative time is the anchor. Chroma-DTW is allowed to refine the anchor
    only when it remains locally consistent; a jump roughly the size of a neighbouring
    note is rejected. This is deliberate: reference guidance exists specifically to
    rescue incorrect sung pitches.
    """
    raw_end=max(float(raw_t[-1]) if len(raw_t) else 0.0,1e-6)
    ref_end=max(float(ref_t[-1]) if len(ref_t) else 0.0,1e-6)
    ratio=ref_end/raw_end
    raw0=float(raw_t[a]); raw1=float(raw_t[b]); raw_mid=.5*(raw0+raw1)
    affine_mid=raw_mid*ratio
    mapped_mid=None
    if mapped is not None and len(mapped)>b:
        mm=.5*(float(mapped[a])+float(mapped[b]))
        # Trust DTW only as a small timing refinement. A pitch-driven hop to an
        # adjacent note is usually hundreds of ms and must not become note authority.
        if np.isfinite(mm) and abs(mm-affine_mid)<=.22:
            mapped_mid=mm
    anchor=.72*mapped_mid+.28*affine_mid if mapped_mid is not None else affine_mid
    dur=max((raw1-raw0)*ratio,.065)
    # Slightly narrower than the full raw segment to avoid adjacent reference notes.
    half=max(.040,.47*dur)
    return max(0.0,anchor-half), min(ref_end,anchor+half), float(anchor), float(mapped_mid if mapped_mid is not None else affine_mid)


def build_targets(raw,sr,reference=None,genre="modern_metalcore"):
    t,midi,voiced,prob=pyin_track(raw,sr,512)
    events=segment_notes(t,midi,voiced,prob)
    key_src=reference if reference is not None else raw
    root,mode,pcs,key_conf=detect_key(key_src,sr,genre)
    ref_t=ref_midi=ref_voiced=ref_prob=mapped=None
    if reference is not None and len(reference)>sr:
        try:
            ref_t,ref_midi,ref_voiced,ref_prob=pyin_track(reference,sr,512)
            # Keep legacy chroma map only as a bounded micro-timing hint. It never owns
            # the event correspondence in v3.
            mapped=reference_map(raw,reference,sr,t)
        except Exception:
            mapped=None

    rows=[]
    previous_target=None
    previous_ref_anchor=None
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
        ref_anchor=-1.0

        if not protected and ref_t is not None:
            r0,r1,ref_anchor,_=_forge_temporal_reference_window(t,a,b,ref_t,mapped)
            estimate=_forge_weighted_reference_note(ref_t,ref_midi,ref_voiced,ref_prob,r0,r1,center)
            if estimate is not None:
                rn,ref_conf,ref_concentration,ref_spread,ref_support=estimate
                ref_distance=abs(float(rn)-center)

                # Reference authority is intentionally independent of raw pitch for a
                # strong temporal match: this is how FORGE repairs a genuinely missed
                # note. Larger corrections demand cleaner/stabler reference evidence.
                close_ok=(ref_distance<=1.80 and ref_conf>=.56 and ref_concentration>=.48 and ref_support>=3)
                rescue_ok=(ref_distance<=5.50 and ref_conf>=.64 and ref_concentration>=.54 and ref_spread<=1.15 and ref_support>=3)
                extreme_ok=(ref_distance<=7.00 and ref_conf>=.82 and ref_concentration>=.70 and ref_spread<=.78 and ref_support>=5)

                # Phrase-continuity guard: never allow the selected reference window to
                # run backwards. This prevents local DTW irregularities from swapping
                # neighbouring notes.
                monotonic_ok=(previous_ref_anchor is None or ref_anchor>=previous_ref_anchor-.035)
                if monotonic_ok and (close_ok or rescue_ok or extreme_ok):
                    target=int(rn)
                    authority="reference_rescue" if ref_distance>1.80 else "reference"
                    previous_ref_anchor=ref_anchor

        if target is None and not protected:
            target=choose_scale_note(center,pcs)
        if target is None:
            target=int(round(center))

        # Octave/register sanity remains mandatory. A valid melodic rescue may be
        # several semitones, but not an accidental octave flip.
        if abs(float(target)-center)>7.0 and not protected:
            target=choose_scale_note(center,pcs)
            authority="scale_register_guard"

        rows.append(dict(event=eid,start_s=float(t[a]),end_s=float(t[b]),raw_center=center,
                         target_midi=int(target),authority=authority,reference_confidence=float(ref_conf),
                         reference_concentration=float(ref_concentration),reference_spread=float(ref_spread),
                         reference_support=int(ref_support),reference_distance_semitones=float(ref_distance),
                         reference_anchor_s=float(ref_anchor),pitch_confidence=med_prob,spectral_flatness=flat,
                         rough_score=rough_score,protected_unpitched=protected))
        previous_target=int(target)
    return pd.DataFrame(rows),(root,mode,pcs,key_conf)
'''

pattern = r'def build_targets\(raw,sr,reference=None,genre="modern_metalcore"\):.*?(?=\n\ndef psola_natural_tune)'
new_src, count = re.subn(pattern, replacement.rstrip(), src, count=1, flags=re.S)
if count != 1:
    raise SystemExit(f"Could not patch build_targets exactly once (matches={count})")
ENGINE.write_text(new_src, encoding="utf-8")
print("FORGE Melody Authority v3 patch applied")
