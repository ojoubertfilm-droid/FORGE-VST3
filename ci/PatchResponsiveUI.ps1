$ErrorActionPreference = 'Stop'
$p = 'Source\PluginEditor.cpp'
$s = Get-Content $p -Raw

# Top tabs: preserve enough width at the minimum editor size.
$s = [regex]::Replace(
    $s,
    'auto tabs = top\.reduced \(420, 18\);\s*tabs\.removeFromRight \(40\);',
    "auto tabs = top.reduced (18);`r`n    tabs.removeFromLeft (355);`r`n    tabs.removeFromRight (10);",
    1)

# Sidebar: reserve the bottom section for Load Reference, Capture, Genre and PRODUCE VOCAL.
$s = $s.Replace(
    'sidebar.removeFromTop (340);',
    'sidebar.removeFromTop (juce::jmax (190, sidebar.getHeight() - 200));')

# Six-knob lead/stack area: dynamic rows so the lower controls and action button remain visible.
$layoutPattern = 'right\.removeFromTop \(42\);\s*auto layoutSix = \[&right\] \(std::initializer_list<juce::Slider\*> ss\)\s*\{\s*for \(auto\* s : ss\) s->setBounds \(right\.removeFromTop \(100\)(?:\.reduced \(120, 4, 4, 4\)|\.withTrimmedLeft \(120\)\.reduced \(4\))\);\s*\};'
$layoutReplacement = @'
right.removeFromTop (32);
    auto layoutSix = [&right] (std::initializer_list<juce::Slider*> ss)
    {
        const int count = juce::jmax (1, (int) ss.size());
        const int rowH = juce::jlimit (48, 86, (right.getHeight() - 96) / count);
        for (auto* slider : ss)
        {
            auto slot = right.removeFromTop (rowH);
            slider->setBounds (slot.withTrimmedLeft (96).reduced (2, 3));
        }
    };
'@
$s = [regex]::Replace($s, $layoutPattern, $layoutReplacement, 1)

# Painted labels follow the exact same responsive row spacing.
$labelPattern = 'for \(int i = 0; i < 6; \+\+i\) \{ g\.setColour \(muted\); g\.setFont \(juce::Font \(10\.0f\)\); g\.drawText \(names\[i\], q\.removeFromTop \(100\.0f\), juce::Justification::centredLeft\); \}'
$labelReplacement = @'
const int labelRow = juce::jlimit (48, 86, (q.getHeight() - 84) / 6);
        for (int i = 0; i < 6; ++i) { g.setColour (muted); g.setFont (juce::Font (10.0f)); g.drawText (names[i], q.removeFromTop ((float) labelRow), juce::Justification::centredLeft); }
'@
$s = [regex]::Replace($s, $labelPattern, $labelReplacement)

# Keep unfinished neural generation out of the install-candidate UI. Source remains for later development.
$s = $s.Replace('    setupButton (neuralTab, "Neural");', "    setupButton (neuralTab, \"Neural\");`r`n    neuralTab.setVisible (false);`r`n    neuralTab.setEnabled (false);")
$s = $s.Replace('    const int tw = juce::jmax (90, tabs.getWidth() / 5);', '    const int tw = juce::jmax (90, tabs.getWidth() / 4);')
$s = [regex]::Replace($s, '\s*neuralTab\.setBounds \(tabs\.removeFromLeft \(tw\)\.reduced \(4\)\);', '', 1)

# If the hidden neural page is reached programmatically, its controls still remain in-bounds.
$neuralPattern = 'diffusion\.setBounds \(right\.removeFromTop \(110\)(?:\.reduced \(120, 6, 4, 6\)|\.withTrimmedLeft \(120\)\.withTrimmedTop \(6\)\.withTrimmedRight \(4\)\.withTrimmedBottom \(6\))\);\s*identity\.setBounds \(right\.removeFromTop \(110\)(?:\.reduced \(120, 6, 4, 6\)|\.withTrimmedLeft \(120\)\.withTrimmedTop \(6\)\.withTrimmedRight \(4\)\.withTrimmedBottom \(6\))\);'
$neuralReplacement = @'
const int neuralRow = juce::jlimit (64, 110, (right.getHeight() - 24) / 2);
        diffusion.setBounds (right.removeFromTop (neuralRow).withTrimmedLeft (96).reduced (4));
        identity.setBounds (right.removeFromTop (neuralRow).withTrimmedLeft (96).reduced (4));
'@
$s = [regex]::Replace($s, $neuralPattern, $neuralReplacement, 1)

# Fail CI if the key layout changes did not actually land.
$required = @(
    'tabs.removeFromLeft (355);',
    'sidebar.getHeight() - 200',
    'const int rowH = juce::jlimit (48, 86',
    'const int labelRow = juce::jlimit (48, 86',
    'neuralTab.setVisible (false);',
    'tabs.getWidth() / 4'
)
foreach ($needle in $required) {
    if (-not $s.Contains($needle)) { throw "Responsive UI patch failed to apply: $needle" }
}

Set-Content $p $s -Encoding utf8
Write-Host 'Responsive FORGE editor patch applied and verified.'
