#!/usr/bin/env python3
"""FORGE offline engine for the Windows VST3 / REAPER build."""
from __future__ import annotations
import argparse, json, math, os, shutil, sys
from pathlib import Path
import numpy as np
import pandas as pd
import soundfile as sf
from scipy import signal
import librosa
import parselmouth
from parselmouth.praat import call

def mono_load(path, target_sr=None):
    y,sr=sf.read(str(path),dtype="float64",always_2d=True); m=y[:,0] if y.shape[1]==1 else np.mean(y[:,:2],axis=1)
    if target_sr and sr!=target_sr: m=librosa.resample(m,orig_sr=sr,target_sr=target_sr); sr=target_sr
    return m.astype(np.float64),int(sr)

def stereo_reference_proxy(path,sr):
    x,rsr=sf.read(str(path),dtype="float64",always_2d=True)
    if rsr!=sr: x=librosa.resample(x.T,orig_sr=rsr,target_sr=sr).T
    if x.shape[1]==1: return x[:,0].astype(np.float64)
    L,R=x[:,0],x[:,1]; mid=.5*(L+R); side=.5*(L-R)
    side_env=np.sqrt(signal.convolve(side**2,np.ones(1024)/1024,mode="same")+1e-12); mid_env=np.sqrt(signal.convolve(mid**2,np.ones(1024)/1024,mode="same")+1e-12)
    mask=np.clip((mid_env-.45*side_env)/(mid_env+1e-9),.15,1.0)
    return (mid*mask).astype(np.float64)

def pyin_track(y,sr,hop=256):
    f0,voiced,prob=librosa.pyin(y.astype(float),fmin=librosa.note_to_hz("A2"),fmax=librosa.note_to_hz("C6"),sr=sr,frame_length=2048,hop_length=hop)
    t=librosa.frames_to_time(np.arange(len(f0)),sr=sr,hop_length=hop); return t,librosa.hz_to_midi(f0),voiced,prob

SCALE_LIBRARY={"major":[0,2,4,5,7,9,11],"natural_minor":[0,2,3,5,7,8,10],"harmonic_minor":[0,2,3,5,7,8,11],"phrygian":[0,1,3,5,7,8,10],"dorian":[0,2,3,5,7,9,10]}
GENRE_PROFILES={
 "modern_metalcore":{"display":"Modern Metalcore","allowed_scales":["natural_minor","harmonic_minor","phrygian","major"],"accuracy_bias":.06,"expression_bias":-.03,"mix":{"hp_hz":82,"deess":.72,"compression":.82,"presence":.70,"saturation":.38},"stack":{"upper_density":.72,"lower_density":.48,"octave_density":.30,"double_tightness":.80}},
 "post_hardcore":{"display":"Post-Hardcore","allowed_scales":["natural_minor","major","dorian","phrygian"],"accuracy_bias":.02,"expression_bias":.05,"mix":{"hp_hz":78,"deess":.64,"compression":.74,"presence":.64,"saturation":.30},"stack":{"upper_density":.78,"lower_density":.36,"octave_density":.22,"double_tightness":.68}},
 "alt_metal":{"display":"Alt Metal","allowed_scales":["natural_minor","major","dorian","phrygian"],"accuracy_bias":-.02,"expression_bias":.08,"mix":{"hp_hz":75,"deess":.58,"compression":.68,"presence":.58,"saturation":.34},"stack":{"upper_density":.55,"lower_density":.42,"octave_density":.20,"double_tightness":.60}},
 "pop_punk":{"display":"Pop-Punk","allowed_scales":["major","natural_minor","dorian"],"accuracy_bias":0.0,"expression_bias":.04,"mix":{"hp_hz":80,"deess":.66,"compression":.76,"presence":.74,"saturation":.24},"stack":{"upper_density":.62,"lower_density":.22,"octave_density":.16,"double_tightness":.74}}}
NOTE_NAMES=["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
def genre_profile(name): return GENRE_PROFILES.get(name,GENRE_PROFILES["modern_metalcore"])
def scale_pcs(root,mode): return {(root+i)%12 for i in SCALE_LIBRARY[mode]}
def key_name(root,mode): return NOTE_NAMES[int(root)%12]+{"major":" Major","natural_minor":" Minor","harmonic_minor":" Harmonic Minor","phrygian":" Phrygian","dorian":" Dorian"}.get(mode," "+mode)

def spectral_event_features(y,sr,start_s,end_s):
    a=max(0,int(start_s*sr)); b=min(len(y),int(end_s*sr)); seg=y[a:b]
    if len(seg)<512:return 0.0,1.0
    try:
        nfft=1024 if len(seg)>=1024 else 512; flat=float(np.median(librosa.feature.spectral_flatness(y=seg.astype(float),n_fft=nfft,hop_length=max(128,nfft//4)))); zcr=float(np.median(librosa.feature.zero_crossing_rate(seg.astype(float),frame_length=nfft,hop_length=max(128,nfft//4))))
    except Exception: flat,zcr=0.0,0.0
    return flat,zcr

def detect_key(y,sr,genre="modern_metalcore"):
    chroma=librosa.feature.chroma_cqt(y=y.astype(float),sr=sr,hop_length=1024); p=np.mean(chroma,axis=1); p_l2=p/(np.linalg.norm(p)+1e-9); p_sum=np.maximum(p,0); p_sum=p_sum/(np.sum(p_sum)+1e-9); profile=genre_profile(genre)
    major=np.array([6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88],float); minor=np.array([6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17],float); major/=np.linalg.norm(major); minor/=np.linalg.norm(minor)
    scores=[]
    for root in range(12):
        if "major" in profile["allowed_scales"]: scores.append((float(np.dot(p_l2,np.roll(major,root))),root,"major"))
        if "natural_minor" in profile["allowed_scales"]: scores.append((float(np.dot(p_l2,np.roll(minor,root))),root,"natural_minor"))
    for root in range(12):
        for mode in profile["allowed_scales"]:
            if mode in ("major","natural_minor"): continue
            pcs=scale_pcs(root,mode); inside=sum(p_sum[i] for i in pcs); outside=1-inside; fit=inside-.55*outside+.18*p_sum[root]+.06*p_sum[(root+7)%12]; prior={"dorian":.055,"phrygian":.070,"harmonic_minor":.085}.get(mode,.07); scores.append((float(.78+.20*fit-prior),root,mode))
    scores.sort(reverse=True); best,second=scores[0],scores[1]; gap=max(0.0,best[0]-second[0]); conf=float(np.clip(.50+gap*8.0,0,1)); root,mode=int(best[1]),str(best[2]); return root,mode,scale_pcs(root,mode),conf

def segment_notes(t,midi,voiced,prob,min_s=.055):
    ok=np.isfinite(midi)&voiced&(prob>.38); events=[]; start=last=None
    for i in range(len(t)):
        if not ok[i]:
            if start is not None and last is not None and t[last]-t[start]>=min_s: events.append((start,last))
            start=last=None; continue
        if start is None: start=last=i; continue
        jump=abs(midi[i]-midi[last]); gap=t[i]-t[last]
        if gap>.055 or (jump>.72 and (t[i]-t[start])>.075):
            if t[last]-t[start]>=min_s: events.append((start,last))
            start=i
        last=i
    if start is not None and last is not None and t[last]-t[start]>=min_s: events.append((start,last))
    return events

def reference_map(raw,ref,sr,raw_t):
    hop=512; Cr=librosa.feature.chroma_stft(y=raw.astype(float),sr=sr,hop_length=hop,n_fft=2048); Cf=librosa.feature.chroma_stft(y=ref.astype(float),sr=sr,hop_length=hop,n_fft=2048); D,wp=librosa.sequence.dtw(X=Cr,Y=Cf,metric="cosine",subseq=True,backtrack=True); wp=wp[::-1]; rt=librosa.frames_to_time(wp[:,0],sr=sr,hop_length=hop); ft=librosa.frames_to_time(wp[:,1],sr=sr,hop_length=hop); order=np.argsort(rt); rt=rt[order]; ft=ft[order]; urt,idx=np.unique(rt,return_index=True); uft=ft[idx]; return np.interp(raw_t,urt,uft,left=uft[0],right=uft[-1])
def choose_scale_note(center,pcs):
    n0=int(round(center)); allowed=[n for n in range(n0-2,n0+3) if n%12 in pcs]; return min(allowed,key=lambda n:abs(n-center)) if allowed else n0

def build_targets(raw,sr,reference=None,genre="modern_metalcore"):
    t,midi,voiced,prob=pyin_track(raw,sr,512); events=segment_notes(t,midi,voiced,prob); key_src=reference if reference is not None else raw; root,mode,pcs,key_conf=detect_key(key_src,sr,genre); ref_t=ref_midi=ref_voiced=ref_prob=mapped=None
    if reference is not None and len(reference)>sr:
        try: ref_t,ref_midi,ref_voiced,ref_prob=pyin_track(reference,sr,512); mapped=reference_map(raw,reference,sr,t)
        except Exception: mapped=None
    rows=[]
    for eid,(a,b) in enumerate(events):
        inds=np.arange(a,b+1); vals=midi[inds]; good=np.isfinite(vals)
        if good.sum()<3: continue
        center=float(np.nanmedian(vals[good])); med_prob=float(np.nanmedian(prob[inds][np.isfinite(prob[inds])])) if np.isfinite(prob[inds]).any() else 0.0; flat,zcr=spectral_event_features(raw,sr,float(t[a]),float(t[b])); rough_score=float(np.clip((.58-med_prob)*2.0+max(0,flat-.12)*2.2+max(0,zcr-.20)*1.4,0,1)); protected=bool((med_prob<.50 and flat>.10) or rough_score>.58); target=None; authority="protected" if protected else "scale"; ref_conf=0.0
        if not protected and mapped is not None:
            r0=float(mapped[a]); r1=float(mapped[b]); rmask=(ref_t>=min(r0,r1)-.05)&(ref_t<=max(r0,r1)+.05)&np.isfinite(ref_midi)&ref_voiced&(ref_prob>.45)
            if rmask.sum()>=3:
                rc=float(np.median(ref_midi[rmask])); ref_conf=float(np.median(ref_prob[rmask])); rn=int(round(rc))
                if abs(rn-center)<=1.45: target=rn; authority="reference"
        if target is None and not protected: target=choose_scale_note(center,pcs)
        if target is None: target=int(round(center))
        rows.append(dict(event=eid,start_s=float(t[a]),end_s=float(t[b]),raw_center=center,target_midi=int(target),authority=authority,reference_confidence=ref_conf,pitch_confidence=med_prob,spectral_flatness=flat,rough_score=rough_score,protected_unpitched=protected))
    return pd.DataFrame(rows),(root,mode,pcs,key_conf)

def psola_natural_tune(y,sr,events,accuracy=.84,expression=.72,repair=.58,timing_tightness=.62,humanize=.72):
    snd=parselmouth.Sound(y,sampling_frequency=sr); manip=call(snd,"To Manipulation",0.005,70,800); tier=call(manip,"Extract pitch tier"); n=int(call(tier,"Get number of points"))
    if n<4:return y.copy()
    tt=np.array([call(tier,"Get time from index",i) for i in range(1,n+1)]); hz=np.array([call(tier,"Get value at index",i) for i in range(1,n+1)]); midi=69+12*np.log2(np.maximum(hz,1e-9)/440); new=midi.copy(); drift_retain=np.interp(expression,[0,1],[.16,.54])*np.interp(humanize,[0,1],[.72,1.12]); modulation_retain=np.interp(expression,[0,1],[.60,1.00])*np.interp(humanize,[0,1],[.78,1.12]); correction_strength=np.interp(accuracy,[0,1],[.45,1.0]); cap_cents=np.interp(humanize,[0,1],[13,29]); attack=np.interp(timing_tightness,[0,1],[.070,.028]); release=np.interp(timing_tightness,[0,1],[.085,.038]); rescue_cents=np.interp(repair,[0,1],[70,190])
    for _,e in events.iterrows():
        if bool(e.get("protected_unpitched",False)): continue
        inds=np.where((tt>=e.start_s)&(tt<=e.end_s))[0]
        if len(inds)<5: continue
        orig=midi[inds].copy(); L=len(orig); win=int(round(.18/.005)); win+=1-win%2; win=min(win,L if L%2 else L-1); slow=signal.savgol_filter(orig,win,2) if win>=7 else orig.copy(); c0=max(1,int(.20*L)); c1=max(c0+2,int(.82*L)); core=np.arange(c0,min(c1,L)); center=float(np.median(slow[core])); drift=slow-center; mod=orig-slow; target=float(e.target_midi); desired=target+drift*drift_retain+mod*modulation_retain; desired=target+np.clip(desired-target,-cap_cents/100,cap_cents/100); phase=np.linspace(0,1,L); ae=np.clip(phase/max(attack/(L*.005),1e-4),0,1); re=np.clip((1-phase)/max(release/(L*.005),1e-4),0,1); edge=.12+.88*np.sin(np.minimum(ae,re)*np.pi/2)**2; vel=np.abs(np.gradient(orig)); motion=np.clip((vel-.035)/.24,0,1); weight=np.clip(edge*(1-.60*motion)*correction_strength,.08,1); shift=np.clip((desired-orig)*weight,-rescue_cents/100,rescue_cents/100); corrected=orig+shift; pred=float(np.median(corrected[core])); bias=(target-pred)*correction_strength; cm=np.zeros(L); cm[core]=1.0; cm=signal.convolve(cm,np.ones(13)/13,mode="same"); corrected+=bias*cm; new[inds]=corrected
    call(tier,"Remove points between",0,len(y)/sr)
    for t,m in zip(tt,new): call(tier,"Add point",float(t),float(440*(2**((m-69)/12))))
    call([tier,manip],"Replace pitch tier"); out=call(manip,"Get resynthesis (overlap-add)").values[0].astype(np.float64)
    if len(out)<len(y):out=np.pad(out,(0,len(y)-len(out)))
    return out[:len(y)]

def ready_to_mix(y,sr):
    out=signal.sosfiltfilt(signal.butter(2,70,btype="highpass",fs=sr,output="sos"),y); w=max(1,int(.24*sr)); rms=np.sqrt(signal.convolve(out**2,np.ones(w)/w,mode="same")+1e-12); active=rms>np.percentile(rms,55); target=np.median(rms[active]) if active.any() else np.median(rms); gdb=np.clip(20*np.log10((target+1e-9)/(rms+1e-9)),-3,3); gdb[~active]=np.minimum(gdb[~active],0); g=10**(gdb/20); g=signal.sosfiltfilt(signal.butter(2,2.2,btype="lowpass",fs=sr,output="sos"),g); out*=g; out*=10**(-6/20)/(np.max(np.abs(out))+1e-12); return out

def _compressor_gain(y,sr,threshold_db=-20,ratio=4.0,attack_ms=5,release_ms=70,max_gr_db=12):
    x=np.abs(y)+1e-9; atk=np.exp(-1/(sr*attack_ms/1000)); rel=np.exp(-1/(sr*release_ms/1000)); env=np.empty_like(x); v=0.0
    for i,samp in enumerate(x): c=atk if samp>v else rel; v=c*v+(1-c)*samp; env[i]=v
    db=20*np.log10(env+1e-9); over=np.maximum(db-threshold_db,0); gr=np.minimum(over*(1-1/ratio),max_gr_db); return 10**(-gr/20)

def mix_assist(y,sr,genre="modern_metalcore",strength=.78):
    prof=genre_profile(genre)["mix"]; st=float(np.clip(strength,0,1)); hp=np.interp(st,[0,1],[65,prof["hp_hz"]]); out=signal.sosfiltfilt(signal.butter(2,hp,btype="highpass",fs=sr,output="sos"),y); lowmid=signal.sosfiltfilt(signal.butter(2,[230,430],btype="bandpass",fs=sr,output="sos"),out); lm_env=np.sqrt(signal.convolve(lowmid**2,np.ones(max(8,int(.035*sr)))/max(8,int(.035*sr)),mode="same")+1e-12); lm_thr=np.percentile(lm_env,72); lm_amt=np.clip((lm_env-lm_thr)/(lm_thr+1e-9),0,1)*(.16+.20*st); out=out-lowmid*lm_amt; comp=prof["compression"]*st; out*=_compressor_gain(out,sr,-25,2.2+1.0*comp,18,115,7); out*=_compressor_gain(out,sr,-17,3.0+2.5*comp,2.5,48,8)
    if sr>26000:
        hi=signal.sosfiltfilt(signal.butter(3,[5200,min(11500,sr*.46)],btype="bandpass",fs=sr,output="sos"),out); he=np.sqrt(signal.convolve(hi**2,np.ones(max(8,int(.012*sr)))/max(8,int(.012*sr)),mode="same")+1e-12); ht=np.percentile(he,78); out-=hi*np.clip((he-ht)/(ht+1e-9),0,1)*(.20+.34*prof["deess"]*st)
    if sr>12000: out+=signal.sosfiltfilt(signal.butter(2,[1800,5200],btype="bandpass",fs=sr,output="sos"),out)*(.035+.075*prof["presence"]*st)
    drive=1.0+1.8*prof["saturation"]*st; out=np.tanh(out*drive)/np.tanh(drive); out*=10**(-4/20)/(np.max(np.abs(out))+1e-12); return out

def perfect_lead(args):
    raw,sr=mono_load(args.input); ref=None
    if args.reference:
        try: ref=stereo_reference_proxy(args.reference,sr)
        except Exception as exc: print("Reference proxy failed; using key-only fallback:",exc,file=sys.stderr)
    prof=genre_profile(args.genre); events,key=build_targets(raw,sr,ref,args.genre); accuracy=float(np.clip(args.accuracy+prof["accuracy_bias"],0,1)); expression=float(np.clip(args.expression+prof["expression_bias"],0,1)); tuned=psola_natural_tune(raw,sr,events,accuracy,expression,args.repair,args.timing_tightness,args.humanize); dry=ready_to_mix(tuned,sr); mixed=mix_assist(dry,sr,args.genre,args.mix_strength); Path(args.output).parent.mkdir(parents=True,exist_ok=True); sf.write(args.output,dry,sr,subtype="PCM_24"); mixed_output=args.mixed_output or str(Path(args.output).with_name(Path(args.output).stem+"_MIXED.wav")); sf.write(mixed_output,mixed,sr,subtype="PCM_24"); protected=int(events.protected_unpitched.sum()) if "protected_unpitched" in events else 0; report={"engine":"FORGE Heavy Vocal","genre":args.genre,"key":{"root_pc":key[0],"mode":key[1],"name":key_name(key[0],key[1]),"confidence":key[3]},"events":events.to_dict(orient="records"),"protected_rough_events":protected,"outputs":{"perfect_dry":str(args.output),"mixed_lead":str(mixed_output)}}; Path(args.output).with_suffix(".json").write_text(json.dumps(report,indent=2)); print(f"FORGE_KEY={key_name(key[0],key[1])}|CONF={key[3]:.3f}|PROTECTED={protected}|EVENTS={len(events)}")

def scale_degree_harmony(note,root,mode,steps=2):
    scale=SCALE_LIBRARY[mode]; tones=[]
    for octv in range(-2,3):
        base=(note//12+octv)*12+root
        for iv in scale: tones.append(base+iv)
    tones=sorted(set(tones)); nearest=min(range(len(tones)),key=lambda i:abs(tones[i]-note)); return int(tones[int(np.clip(nearest+steps,0,len(tones)-1))])

def render_part(lead,sr,events,targets,seed,expr=.80,timing_mean_ms=0.0,timing_sd_ms=8.0,gain_jitter_db=.65):
    rng=np.random.default_rng(seed); snd=parselmouth.Sound(lead,sampling_frequency=sr); manip=call(snd,"To Manipulation",0.005,70,850); tier=call(manip,"Extract pitch tier"); n=int(call(tier,"Get number of points"))
    if n<4:return np.zeros_like(lead)
    tt=np.array([call(tier,"Get time from index",i) for i in range(1,n+1)]); hz=np.array([call(tier,"Get value at index",i) for i in range(1,n+1)]); midi=69+12*np.log2(np.maximum(hz,1e-9)/440); new=midi.copy(); gate=np.zeros(len(lead)); gains=np.ones(len(lead))
    for idx,e in events.iterrows():
        target=targets.get(int(idx))
        if target is None: continue
        inds=np.where((tt>=e.start_s)&(tt<=e.end_s))[0]
        if len(inds)<5: continue
        orig=midi[inds]; L=len(orig); center=float(np.median(orig)); rate=rng.uniform(4.5,6.2); phase=rng.uniform(0,2*np.pi); tloc=np.arange(L)*.005; vib=(rng.uniform(2.0,4.5)/100)*np.sin(2*np.pi*rate*tloc+phase); offset=rng.normal(0,3.5)/100; desired=float(target)+offset+expr*(orig-center)+vib; ph=np.linspace(0,1,L); edge=np.minimum(np.clip(ph/.14,0,1),np.clip((1-ph)/.16,0,1)); edge=.12+.88*np.sin(edge*np.pi/2)**2; new[inds]=orig+(desired-orig)*edge; jitter=rng.normal(timing_mean_ms,timing_sd_ms)/1000; s=max(0,int((e.start_s+jitter)*sr)); en=min(len(gate),int((e.end_s+jitter)*sr));
        if en>s: gate[s:en]=1; gains[s:en]*=10**(rng.normal(0,gain_jitter_db)/20)
    call(tier,"Remove points between",0,len(lead)/sr)
    for t,m in zip(tt,new): call(tier,"Add point",float(t),float(440*(2**((m-69)/12))))
    call([tier,manip],"Replace pitch tier"); y=call(manip,"Get resynthesis (overlap-add)").values[0].astype(np.float64); y=np.pad(y,(0,max(0,len(lead)-len(y))))[:len(lead)]; fade=max(1,int(.018*sr)); gate=np.clip(signal.convolve(gate,np.ones(fade)/fade,mode="same"),0,1); gains=signal.sosfiltfilt(signal.butter(2,12,btype="lowpass",fs=sr,output="sos"),gains); y*=gate*gains; p=np.max(np.abs(y))+1e-12
    if p>10**(-8/20): y*=10**(-8/20)/p
    return y

def build_stack(args):
    lead,sr=mono_load(args.input); ref=None
    if args.reference:
        try: ref=stereo_reference_proxy(args.reference,sr)
        except Exception: pass
    sidecar=Path(args.input).with_suffix(".json"); events=key=None
    if sidecar.exists():
        try:
            cached=json.loads(sidecar.read_text()); rows=cached.get("events") or []; k=cached.get("key") or {}
            if rows and "root_pc" in k and "mode" in k: events=pd.DataFrame(rows); root=int(k["root_pc"]); mode=str(k["mode"]); key=(root,mode,scale_pcs(root,mode),float(k.get("confidence",.5)))
        except Exception: pass
    if events is None or key is None: events,key=build_targets(lead,sr,ref,args.genre)
    root,mode,pcs,key_conf=key; prof=genre_profile(args.genre)["stack"]; outdir=Path(args.output_dir); outdir.mkdir(parents=True,exist_ok=True); sf.write(outdir/"01_MASTER_LEAD_DRY.wav",lead,sr,subtype="PCM_24")
    mixed_side=Path(args.input).with_name("mixed_lead.wav"); mixed_lead=None
    if mixed_side.exists(): mixed_lead,_=mono_load(mixed_side,sr); sf.write(outdir/"02_MASTER_LEAD_MIXED.wav",mixed_lead,sr,subtype="PCM_24")
    energy_src=ref if ref is not None else lead; rms=librosa.feature.rms(y=energy_src.astype(float),frame_length=2048,hop_length=512)[0]; et=librosa.frames_to_time(np.arange(len(rms)),sr=sr,hop_length=512); ev_energy=[float(np.mean(rms[(et>=e.start_s)&(et<=e.end_s)])) if ((et>=e.start_s)&(et<=e.end_s)).any() else 0.0 for _,e in events.iterrows()]; hd=np.clip(.55*args.stack_size+.45*args.harmony_intensity,0,1); upper_density=np.clip(.45*hd+.55*prof["upper_density"],0,1); lower_density=np.clip(.45*hd+.55*prof["lower_density"],0,1); oct_density=np.clip(.50*args.stack_size+.50*prof["octave_density"],0,1); uq=float(np.interp(upper_density,[0,1],[92,38])); lq=float(np.interp(lower_density,[0,1],[96,52])); oq=float(np.interp(oct_density,[0,1],[99,70])); tu=np.percentile(ev_energy,uq) if ev_energy else 0; tl=np.percentile(ev_energy,lq) if ev_energy else 0; to=np.percentile(ev_energy,oq) if ev_energy else 0; upper={}; lower={}; high={}; low={}; dl={}; dr={}
    for i,e in events.iterrows():
        if bool(e.get("protected_unpitched",False)): continue
        leadnote=int(e.target_midi); dl[i]=leadnote; dr[i]=leadnote; en=ev_energy[i] if i<len(ev_energy) else 0
        if en>=tu: upper[i]=scale_degree_harmony(leadnote,root,mode,+2)
        if en>=tl: lower[i]=scale_degree_harmony(leadnote,root,mode,-2)
        if en>=to: high[i]=leadnote+12; low[i]=leadnote-12
    spread=np.interp(args.width,[0,1],[.42,1.35]); tight_base=np.clip(.55*args.tightness+.45*prof["double_tightness"],0,1); timing_scale=np.interp(tight_base,[0,1],[1.35,.55])*spread; char_expr=np.interp(args.character,[0,1],[.91,.73]); gain_j=np.interp(args.character,[0,1],[.30,.82]); harm_gain=np.interp(args.harmony_intensity,[0,1],[.32,.95]); high_gain=np.interp(args.octave_blend,[0,1],[.40,.95]); low_gain=np.interp(args.octave_blend,[0,1],[.95,.38]); parts={"03_DOUBLE_L.wav":render_part(lead,sr,events,dl,101,.82*char_expr,-8*spread,5.5*timing_scale,gain_j),"04_DOUBLE_R.wav":render_part(lead,sr,events,dr,102,.80*char_expr,10*spread,6.5*timing_scale,gain_j),"05_UPPER_HARMONY.wav":render_part(lead,sr,events,upper,201,.74*char_expr,0,8.5*timing_scale,gain_j*.90)*harm_gain,"06_LOWER_HARMONY.wav":render_part(lead,sr,events,lower,202,.75*char_expr,3*spread,9*timing_scale,gain_j*.90)*harm_gain,"07_HIGH_OCTAVE.wav":render_part(lead,sr,events,high,301,.68*char_expr,0,10*timing_scale,gain_j)*high_gain,"08_LOW_OCTAVE.wav":render_part(lead,sr,events,low,302,.70*char_expr,4*spread,10*timing_scale,gain_j)*low_gain}
    for name,y in parts.items(): sf.write(outdir/name,y,sr,subtype="PCM_24")
    base=mixed_lead if mixed_lead is not None else lead; L=base.copy(); R=base.copy()
    def add_stereo(y,pan,gain):
        nonlocal L,R; ang=(pan+1)*np.pi/4; L+=y*np.cos(ang)*gain; R+=y*np.sin(ang)*gain
    add_stereo(parts["03_DOUBLE_L.wav"],-.78,.52); add_stereo(parts["04_DOUBLE_R.wav"],.78,.52); add_stereo(parts["05_UPPER_HARMONY.wav"],-.46,.42); add_stereo(parts["06_LOWER_HARMONY.wav"],.46,.36); add_stereo(parts["07_HIGH_OCTAVE.wav"],-.20,.25); add_stereo(parts["08_LOW_OCTAVE.wav"],.20,.22); preview=np.column_stack([L,R]); preview*=10**(-3/20)/(np.max(np.abs(preview))+1e-12); sf.write(outdir/"09_STACK_REFERENCE_MIX.wav",preview,sr,subtype="PCM_24"); print(f"STACK_KEY={key_name(root,mode)}|CONF={key_conf:.3f}|STATUS=guide_stems")

def self_test(args):
    sr=44100
    def tone(freq,dur,amp=.16):
        n=int(sr*dur); t=np.arange(n)/sr; y=amp*np.sin(2*np.pi*freq*t); fade=min(int(.02*sr),n//3)
        if fade>2: ramp=np.linspace(0,1,fade); y[:fade]*=ramp; y[-fade:]*=ramp[::-1]
        return y
    seq=np.concatenate([tone(220,.32),tone(261.626,.32),tone(329.628,.32),tone(391.995,.32)]); rng=np.random.default_rng(45); raw=np.concatenate([seq,.025*rng.standard_normal(int(.22*sr))]); events,key=build_targets(raw,sr,None,"modern_metalcore")
    if len(events)<3: raise RuntimeError("Pitch analyzer did not detect synthetic vocal notes.")
    tuned=psola_natural_tune(raw,sr,events,.88,.68,.62,.70,.68); dry=ready_to_mix(tuned,sr); mixed=mix_assist(dry,sr,"modern_metalcore",.82)
    for name,x in (("dry",dry),("mixed",mixed)):
        if not np.all(np.isfinite(x)): raise RuntimeError(name+" contains NaN/Inf")
        if np.max(np.abs(x))>1.001: raise RuntimeError(name+" clips")
    print("FORGE_SELF_TEST=PASS"); print(f"EVENTS={len(events)}|PIPELINE=key+tune+mix")

def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest="cmd",required=True); p=sub.add_parser("perfect-lead"); p.add_argument("--input",required=True); p.add_argument("--reference"); p.add_argument("--output",required=True); p.add_argument("--mixed-output"); p.add_argument("--genre",choices=list(GENRE_PROFILES),default="modern_metalcore"); p.add_argument("--accuracy",type=float,default=.86); p.add_argument("--expression",type=float,default=.70); p.add_argument("--repair",type=float,default=.62); p.add_argument("--timing-tightness",type=float,default=.68); p.add_argument("--humanize",type=float,default=.70); p.add_argument("--mix-strength",type=float,default=.78); p.set_defaults(fn=perfect_lead); st=sub.add_parser("build-stack"); st.add_argument("--input",required=True); st.add_argument("--reference"); st.add_argument("--output-dir",required=True); st.add_argument("--genre",choices=list(GENRE_PROFILES),default="modern_metalcore"); st.add_argument("--stack-size",type=float,default=.78); st.add_argument("--width",type=float,default=.82); st.add_argument("--tightness",type=float,default=.72); st.add_argument("--harmony-intensity",type=float,default=.74); st.add_argument("--octave-blend",type=float,default=.52); st.add_argument("--character",type=float,default=.66); st.add_argument("--diffusion-steps",type=int,default=50); st.add_argument("--identity-focus",type=float,default=.70); st.add_argument("--hosted-neural",action="store_true"); st.set_defaults(fn=build_stack); q=sub.add_parser("self-test"); q.set_defaults(fn=self_test); a=ap.parse_args(); a.fn(a)
if __name__=="__main__": main()
