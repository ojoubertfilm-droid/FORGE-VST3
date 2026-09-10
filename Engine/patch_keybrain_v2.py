#!/usr/bin/env python3
from pathlib import Path
import re

p = Path(__file__).with_name('forge_engine.py')
s = p.read_text(encoding='utf-8')
new = r'''def detect_key(y,sr,genre="modern_metalcore"):
    """Heavy-vocal key/mode detector with tonic-aware modal promotion.

    The detector intentionally prefers a conventional major/minor parent when
    the audio does not contain enough evidence to establish a modal tonic.
    Phrygian/Dorian/Harmonic Minor are promoted only when BOTH the characteristic
    scale degree and the proposed tonic are supported. This avoids the common
    failure where a strong tonic is mistaken for the b2 of a neighboring
    Phrygian key.
    """
    chroma = librosa.feature.chroma_cqt(y=y.astype(float), sr=sr, hop_length=1024)
    p = np.mean(chroma, axis=1)
    p_l2 = p / (np.linalg.norm(p) + 1e-9)
    p_sum = np.maximum(p, 0.0)
    p_sum = p_sum / (np.sum(p_sum) + 1e-9)
    profile = genre_profile(genre)

    # Modest phrase-boundary evidence. Useful for vocal/reference material, but
    # deliberately weak enough that a pickup or non-tonic ending cannot dictate
    # the whole key estimate.
    nframes = chroma.shape[1]
    edge_n = max(1, int(round(nframes * 0.16)))
    edge = np.mean(np.concatenate([chroma[:, :edge_n], chroma[:, -edge_n:]], axis=1), axis=1)
    edge = np.maximum(edge, 0.0)
    edge = edge / (np.sum(edge) + 1e-9)

    major = np.array([6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88], float)
    minor = np.array([6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17], float)
    major /= np.linalg.norm(major)
    minor /= np.linalg.norm(minor)

    def mass(root, degree=0):
        return float(p_sum[(root + degree) % 12])

    def edge_mass(root):
        return float(edge[root % 12])

    def tonic_salience(root, is_minor=True):
        third = 3 if is_minor else 4
        # Root is the strongest discriminator. Fifth/third keep power-chord and
        # sparse heavy arrangements from being unfairly penalized.
        return (mass(root, 0)
                + 0.42 * mass(root, 7)
                + 0.28 * mass(root, third)
                + 0.24 * edge_mass(root))

    def base_score(root, mode):
        is_minor = mode != "major"
        template = minor if is_minor else major
        corr = float(np.dot(p_l2, np.roll(template, root)))
        sal = tonic_salience(root, is_minor)
        third_pref = ((mass(root, 3) - mass(root, 4)) if is_minor
                      else (mass(root, 4) - mass(root, 3)))
        return corr + 0.105 * sal + 0.022 * third_pref

    def modal_adjust(root, characteristic_degree, competing_degree, prior):
        characteristic = mass(root, characteristic_degree)
        competing = mass(root, competing_degree)
        tonic = mass(root, 0)
        delta = characteristic - competing

        # Characteristic-note evidence is capped. One loud pitch may suggest a
        # mode, but it is not allowed to overwhelm the evidence for the tonic.
        evidence = float(np.clip(1.15 * delta, -0.045, 0.060))
        if characteristic < 0.018:
            evidence -= 0.045
        if delta < 0.004:
            evidence -= 0.035

        # Critical modal-tonic gate: if the proposed characteristic note is much
        # stronger than the proposed tonic, it is often the true tonic itself
        # (e.g. A being misread as G# Phrygian's b2).
        ratio = tonic / (characteristic + 1e-9)
        if ratio < 0.42:
            evidence -= 0.090 * (1.0 - ratio / 0.42)
        elif ratio < 0.65:
            evidence -= 0.030 * (1.0 - (ratio - 0.42) / 0.23)

        median_mass = float(np.median(p_sum))
        if tonic < 0.72 * median_mass:
            evidence -= 0.045

        return evidence - prior

    scores = []
    natural_minor_scores = []
    salience_cache = {}

    for root in range(12):
        salience_cache[(root, False)] = tonic_salience(root, False)
        salience_cache[(root, True)] = tonic_salience(root, True)

        if "major" in profile["allowed_scales"]:
            sc = base_score(root, "major")
            scores.append((sc, root, "major"))

        if "natural_minor" in profile["allowed_scales"]:
            # Small conventional-parent prior. Modal keys can still win, but
            # only with affirmative evidence.
            sc = base_score(root, "natural_minor") + 0.014
            row = (sc, root, "natural_minor")
            scores.append(row)
            natural_minor_scores.append(row)

        min_base = base_score(root, "natural_minor")
        if "phrygian" in profile["allowed_scales"]:
            scores.append((min_base + modal_adjust(root, 1, 2, 0.018), root, "phrygian"))
        if "dorian" in profile["allowed_scales"]:
            scores.append((min_base + modal_adjust(root, 9, 8, 0.020), root, "dorian"))
        if "harmonic_minor" in profile["allowed_scales"]:
            scores.append((min_base + modal_adjust(root, 11, 10, 0.017), root, "harmonic_minor"))

    scores.sort(reverse=True, key=lambda x: x[0])
    best = scores[0]

    # Conservative modal-collapse rule. If a modal candidate barely beats a
    # natural-minor candidate whose tonic is materially stronger, report the
    # natural minor parent instead of inventing an exotic tonic.
    if best[2] in ("phrygian", "dorian", "harmonic_minor") and natural_minor_scores:
        natural_minor_scores.sort(reverse=True, key=lambda x: x[0])
        nat = natural_minor_scores[0]
        best_sal = salience_cache[(best[1], True)]
        nat_sal = salience_cache[(nat[1], True)]
        if nat[0] >= best[0] - 0.050 and nat_sal > best_sal * 1.12:
            best = nat

    # Confidence is the margin against the strongest *different key/mode* after
    # the conservative selection. Keep ambiguous decisions visibly ambiguous.
    others = [x for x in scores if not (x[1] == best[1] and x[2] == best[2])]
    second = others[0] if others else best
    gap = max(0.0, best[0] - second[0])
    conf = float(np.clip(0.42 + gap * 7.0, 0.0, 0.96))
    if best is not scores[0]:
        conf = min(conf, 0.69)

    root, mode = int(best[1]), str(best[2])
    return root, mode, scale_pcs(root, mode), conf
'''
pat = r'def detect_key\(y,sr,genre="modern_metalcore"\):.*?(?=\ndef segment_notes\()'
out, n = re.subn(pat, new.rstrip() + "\n", s, flags=re.S)
if n != 1:
    raise SystemExit(f'KeyBrain patch expected one detect_key() function, found {n}')
p.write_text(out, encoding='utf-8')
print('FORGE_KEYBRAIN_V3=APPLIED')
