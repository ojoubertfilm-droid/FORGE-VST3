$ErrorActionPreference = 'Stop'
$p = 'Source\PluginEditor.cpp'
$s = Get-Content $p -Raw

# Top tabs must fit at the minimum editor width instead of assuming a 1400px host window.
$s = $s.Replace('    auto tabs = top.reduced (420, 18);`n    tabs.removeFromRight (40);', '    auto tabs = top.reduced (18);`n    tabs.removeFromLeft (355);`n    tabs.removeFromRight (10);')
$s = $s.Replace('    auto tabs = top.reduced (420, 18);\r\n    tabs.removeFromRight (40);', '    auto tabs = top.reduced (18);\r\n    tabs.removeFromLeft (355);\r\n    tabs.removeFromRight (10);')

# Always leave enough sidebar room for Load Reference, Capture, Genre and PRODUCE VOCAL.
$s = $s.Replace('    sidebar.removeFromTop (340);', '    sidebar.removeFromTop (juce::jmax (190, sidebar.getHeight() - 200));')

# Make the six lead/stack controls responsive instead of consuming a hard-coded 600px vertically.
$old = @'
    right.removeFromTop (42);
    auto layoutSix = [&right] (std::initializer_list<juce::Slider*> ss)
    {
        for (auto* s : ss) s->setBounds (right.removeFromTop (100).reduced (120, 4, 4, 4));
    };
'@
$new = @'
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
$s = $s.Replace($old, $new)

# The CI compatibility patch may already have converted Rectangle::reduced calls. Support that form too.
$old2 = @'
    right.removeFromTop (42);
    auto layoutSix = [&right] (std::initializer_list<juce::Slider*> ss)
    {
        for (auto* s : ss) s->setBounds (right.removeFromTop (100).withTrimmedLeft (120).reduced (4));
    };
'@
$s = $s.Replace($old2, $new)

# Responsive labels beside those controls.
$s = $s.Replace('        for (int i = 0; i < 6; ++i) { g.setColour (muted); g.setFont (juce::Font (10.0f)); g.drawText (names[i], q.removeFromTop (100.0f), juce::Justification::centredLeft); }', '        const int labelRow = juce::jlimit (48, 86, (q.getHeight() - 84) / 6);`n        for (int i = 0; i < 6; ++i) { g.setColour (muted); g.setFont (juce::Font (10.0f)); g.drawText (names[i], q.removeFromTop ((float) labelRow), juce::Justification::centredLeft); }')

# Keep the neural controls inside the panel if that page is opened.
$s = $s.Replace('        diffusion.setBounds (right.removeFromTop (110).reduced (120, 6, 4, 6));`n        identity.setBounds (right.removeFromTop (110).reduced (120, 6, 4, 6));', '        const int neuralRow = juce::jlimit (64, 110, (right.getHeight() - 24) / 2);`n        diffusion.setBounds (right.removeFromTop (neuralRow).withTrimmedLeft (96).reduced (4));`n        identity.setBounds (right.removeFromTop (neuralRow).withTrimmedLeft (96).reduced (4));')
$s = $s.Replace('        diffusion.setBounds (right.removeFromTop (110).withTrimmedLeft (120).withTrimmedTop (6).withTrimmedRight (4).withTrimmedBottom (6));`n        identity.setBounds (right.removeFromTop (110).withTrimmedLeft (120).withTrimmedTop (6).withTrimmedRight (4).withTrimmedBottom (6));', '        const int neuralRow = juce::jlimit (64, 110, (right.getHeight() - 24) / 2);`n        diffusion.setBounds (right.removeFromTop (neuralRow).withTrimmedLeft (96).reduced (4));`n        identity.setBounds (right.removeFromTop (neuralRow).withTrimmedLeft (96).reduced (4));')

Set-Content $p $s -Encoding utf8
Write-Host 'Responsive FORGE editor patch applied.'
