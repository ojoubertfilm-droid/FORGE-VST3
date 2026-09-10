#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
editor = (root / "Source" / "PluginEditor.cpp").read_text(encoding="utf-8")
processor = (root / "Source" / "PluginProcessor.cpp").read_text(encoding="utf-8")
bridge = (root / "Source" / "ForgeEngineBridge.cpp").read_text(encoding="utf-8")
engine = (root / "Engine" / "forge_engine.py").read_text(encoding="utf-8")

required_editor = {
    "Load Reference button": "loadReferenceButton.onClick = [this] { openReferenceChooser(); }",
    "Capture button": "captureButton.onClick = [this] { processor.toggleCapture(); }",
    "Produce button": "produceButton.onClick = [this] { processor.produceVocal(); }",
    "Perfect Lead button": "perfectButton.onClick = [this] { processor.perfectLead(); }",
    "Stack button": "stackButton.onClick = [this] { processor.buildStack (false); }",
    "Export button": "exportFolderButton.onClick = [this] { processor.getExportDir().revealToUser(); }",
}

for name, needle in required_editor.items():
    if needle not in editor:
        raise SystemExit(f"WIRING FAIL: {name} callback missing")

lead_params = ["accuracy", "expression", "repair", "timingTightness", "humanize", "mixStrength"]
stack_params = ["stackSize", "width", "tightness", "harmonyIntensity", "octaveBlend", "character"]
for pid in lead_params + stack_params:
    if f'getRawParameterValue("{pid}")' not in processor and f'getRawParameterValue ("{pid}")' not in processor:
        raise SystemExit(f"WIRING FAIL: processor does not read {pid}")

bridge_flags = {
    "accuracy": "--accuracy", "expression": "--expression", "repair": "--repair",
    "timingTightness": "--timing-tightness", "humanize": "--humanize", "mixStrength": "--mix-strength",
    "stackSize": "--stack-size", "width": "--width", "tightness": "--tightness",
    "harmonyIntensity": "--harmony-intensity", "octaveBlend": "--octave-blend", "character": "--character",
}
for pid, flag in bridge_flags.items():
    if flag not in bridge:
        raise SystemExit(f"WIRING FAIL: bridge does not forward {pid} ({flag})")
    if flag not in engine:
        raise SystemExit(f"WIRING FAIL: engine does not accept {pid} ({flag})")

required_processor = [
    "engine.runPerfectLead", "engine.runBuildStack", "writeLatestExportMarker", "loadProcessedAudio",
    "captureBuffer.setSample", "processedBuffer.load", "processedBuffer.store",
]
for needle in required_processor:
    if needle not in processor:
        raise SystemExit(f"WIRING FAIL: missing processor path {needle}")

# Neural is intentionally not certified. The UI must communicate that instead of presenting it as ready.
if "NEURAL FULL-SONG EXPORT LOCKED" not in editor:
    raise SystemExit("WIRING FAIL: experimental neural path is not visibly locked")

print("FORGE_UI_ENGINE_WIRING=PASS")
print("CORE_ACTIONS=load-reference+capture+perfect-lead+produce-vocal+build-stack+export")
print("LEAD_CONTROLS=" + "+".join(lead_params))
print("STACK_CONTROLS=" + "+".join(stack_params))
