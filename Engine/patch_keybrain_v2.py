#!/usr/bin/env python3
from pathlib import Path
import re

p = Path(__file__).with_name('forge_engine.py')
s = p.read_text(encoding='utf-8')
new = r'''def detect_key(y,sr,genre="modern_metalcore"):
    """Heavy-vocal key/mode detector with conservative modal promotion.

    All candidates share the same profile-score scale. Natural minor is the
    parent/default for ambiguous minor or pentatonic heavy music. Phrygian,
    Dorian, and Harmonic Minor only outrank it when their characteristic note
    is actually supported by the reference audio.
    """
    chroma=librosa.feature.chroma_cqt(y=y.astype(float),sr=sr,hop_length=1024)
    p=np.mean(chroma,axis=1)
    p_l2=p/(np.linalg.norm(p)+1e-9)
    p_sum=np.maximum(p,0); p_sum=p_sum/(np.sum(p_sum)+1e-9)
    profile=genre_profile(genre)
    major=np.array([6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88],float)
    minor=np.array([6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17],float)
    major/=np.linalg.norm(major); minor/=np.linalg.norm(minor)
    scores=[]

    def mass(root,degree): return float(p_sum[(root+degree)%12])
    def tonic_support(root,is_minor):
        third=3 if is_minor else 4
        # Heavy music can omit thirds, so tonic/fifth carry more weight than a
        # pop-key estimator, but the third still helps relative-major ambiguity.
        return .085*mass(root,0)+.040*mass(root,7)+.028*mass(root,third)
    def variant_evidence(delta,positive_mass,minimum=.018):
        # Modal variants need affirmative evidence. If both competing notes are
        # absent, stay in Natural Minor instead of inventing an exotic mode.
        score=2.2*delta
        if positive_mass < minimum: score-=.060
        if delta < .004: score-=.045
        return score

    for root in range(12):
        maj_base=float(np.dot(p_l2,np.roll(major,root)))+tonic_support(root,False)
        min_base=float(np.dot(p_l2,np.roll(minor,root)))+tonic_support(root,True)
        if "major" in profile["allowed_scales"]:
            scores.append((maj_base+.14*(mass(root,4)-mass(root,3)),root,"major"))
        if "natural_minor" in profile["allowed_scales"]:
            scores.append((min_base,root,"natural_minor"))
        if "phrygian" in profile["allowed_scales"]:
            b2,n2=mass(root,1),mass(root,2)
            scores.append((min_base+variant_evidence(b2-n2,b2)-.008,root,"phrygian"))
        if "dorian" in profile["allowed_scales"]:
            n6,b6=mass(root,9),mass(root,8)
            scores.append((min_base+variant_evidence(n6-b6,n6)-.012,root,"dorian"))
        if "harmonic_minor" in profile["allowed_scales"]:
            maj7,b7=mass(root,11),mass(root,10)
            scores.append((min_base+variant_evidence(maj7-b7,maj7)-.010,root,"harmonic_minor"))

    scores.sort(reverse=True,key=lambda x:x[0])
    best,second=scores[0],scores[1]
    gap=max(0.0,best[0]-second[0])
    conf=float(np.clip(.42+gap*7.5,0,1))
    root,mode=int(best[1]),str(best[2])
    return root,mode,scale_pcs(root,mode),conf
'''
pat=r'def detect_key\(y,sr,genre="modern_metalcore"\):.*?(?=\ndef segment_notes\()'
out,n=re.subn(pat,new.rstrip()+"\n",s,flags=re.S)
if n != 1:
    raise SystemExit(f'KeyBrain patch expected one detect_key() function, found {n}')
p.write_text(out,encoding='utf-8')
print('FORGE_KEYBRAIN_V2=APPLIED')
