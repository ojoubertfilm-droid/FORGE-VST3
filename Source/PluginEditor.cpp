#include "PluginEditor.h"
#include <cmath>

namespace
{
    const auto bg        = juce::Colour (0xff0a0e10);
    const auto panel     = juce::Colour (0xff12181b);
    const auto panel2    = juce::Colour (0xff182024);
    const auto border    = juce::Colour (0xff2a3539);
    const auto text      = juce::Colour (0xffedf3f0);
    const auto muted     = juce::Colour (0xff899796);
    const auto green     = juce::Colour (0xff39ef83);
    const auto greenDark = juce::Colour (0xff113922);
    const auto amber     = juce::Colour (0xffffbd45);

    void panelBox (juce::Graphics& g, juce::Rectangle<float> r, float radius = 10.0f)
    {
        g.setColour (panel);
        g.fillRoundedRectangle (r, radius);
        g.setColour (border);
        g.drawRoundedRectangle (r.reduced (0.5f), radius, 1.0f);
    }

    void title (juce::Graphics& g, juce::Rectangle<float> r, const juce::String& a, const juce::String& b)
    {
        g.setColour (text);
        g.setFont (juce::Font (19.0f, juce::Font::bold));
        g.drawText (a, r.removeFromTop (28.0f), juce::Justification::centredLeft);
        g.setColour (muted);
        g.setFont (juce::Font (9.5f, juce::Font::plain));
        g.drawText (b.toUpperCase(), r.removeFromTop (18.0f), juce::Justification::centredLeft);
    }
}

ForgeLookAndFeel::ForgeLookAndFeel()
{
    setColour (juce::Label::textColourId, text);
    setColour (juce::TextButton::textColourOffId, text);
    setColour (juce::TextButton::textColourOnId, text);
    setColour (juce::ComboBox::textColourId, text);
    setColour (juce::ComboBox::backgroundColourId, panel2);
    setColour (juce::ComboBox::outlineColourId, border);
    setColour (juce::ComboBox::arrowColourId, muted);
    setColour (juce::PopupMenu::backgroundColourId, panel2);
    setColour (juce::PopupMenu::textColourId, text);
    setColour (juce::PopupMenu::highlightedBackgroundColourId, greenDark);
}

void ForgeLookAndFeel::drawButtonBackground (juce::Graphics& g, juce::Button& b,
                                              const juce::Colour&, bool hover, bool down)
{
    auto r = b.getLocalBounds().toFloat().reduced (0.5f);
    auto fill = b.getToggleState() ? greenDark : panel2;
    if (hover) fill = fill.brighter (0.08f);
    if (down) fill = fill.darker (0.15f);
    g.setColour (fill);
    g.fillRoundedRectangle (r, 7.0f);
    g.setColour (b.getToggleState() ? green : border);
    g.drawRoundedRectangle (r, 7.0f, b.getToggleState() ? 1.5f : 1.0f);
}

void ForgeLookAndFeel::drawButtonText (juce::Graphics& g, juce::TextButton& b, bool, bool)
{
    g.setColour (b.isEnabled() ? text : muted.withAlpha (0.55f));
    g.setFont (juce::Font (13.0f, juce::Font::bold));
    g.drawFittedText (b.getButtonText(), b.getLocalBounds().reduced (8, 4), juce::Justification::centred, 2);
}

void ForgeLookAndFeel::drawRotarySlider (juce::Graphics& g, int x, int y, int w, int h,
                                         float pos, float start, float end, juce::Slider&)
{
    auto size = (float) juce::jmin (w, h) - 10.0f;
    auto r = juce::Rectangle<float> ((float) x + ((float) w - size) * 0.5f,
                                     (float) y + ((float) h - size) * 0.5f, size, size);
    auto c = r.getCentre();
    auto radius = r.getWidth() * 0.5f - 4.0f;
    g.setColour (juce::Colour (0xff07090a));
    g.fillEllipse (r);
    g.setColour (border);
    g.drawEllipse (r, 2.0f);
    juce::Path track, value;
    track.addCentredArc (c.x, c.y, radius, radius, 0.0f, start, end, true);
    value.addCentredArc (c.x, c.y, radius, radius, 0.0f, start, start + pos * (end - start), true);
    g.setColour (juce::Colour (0xff30383b));
    g.strokePath (track, juce::PathStrokeType (5.0f));
    g.setColour (green);
    g.strokePath (value, juce::PathStrokeType (5.0f));
}

FORGEAudioProcessorEditor::FORGEAudioProcessorEditor (FORGEAudioProcessor& p)
    : AudioProcessorEditor (&p), processor (p)
{
    setLookAndFeel (&forgeLaf);
    setResizable (true, true);
    setResizeLimits (1050, 700, 1800, 1200);
    setSize (1400, 900);

    setupButton (captureTab, "Capture");
    setupButton (leadTab, "Perfect Lead");
    setupButton (stackTab, "Build Stack");
    setupButton (neuralTab, "Neural");
    setupButton (exportTab, "Export");
    captureTab.onClick = [this] { setPage (Page::capture); };
    leadTab.onClick = [this] { setPage (Page::lead); };
    stackTab.onClick = [this] { setPage (Page::stack); };
    neuralTab.onClick = [this] { setPage (Page::neural); };
    exportTab.onClick = [this] { setPage (Page::exportPage); };

    setupButton (loadReferenceButton, "Load Reference");
    setupButton (captureButton, "Capture Vocal");
    setupButton (produceButton, "PRODUCE VOCAL");
    setupButton (perfectButton, "Perfect Lead");
    setupButton (stackButton, "Build Stack");
    setupButton (exportFolderButton, "Open Export Folder");

    loadReferenceButton.onClick = [this] { openReferenceChooser(); };
    captureButton.onClick = [this] { processor.toggleCapture(); };
    produceButton.onClick = [this] { processor.produceVocal(); };
    perfectButton.onClick = [this] { processor.perfectLead(); };
    stackButton.onClick = [this] { processor.buildStack (false); };
    exportFolderButton.onClick = [this] { processor.getExportDir().revealToUser(); };

    auditionProcessed.setToggleState (true, juce::dontSendNotification);
    auditionProcessed.onClick = [this] { processor.setAuditionProcessed (auditionProcessed.getToggleState()); };
    addAndMakeVisible (auditionProcessed);

    genreBox.addItem ("Modern Metalcore", 1);
    genreBox.addItem ("Post-Hardcore", 2);
    genreBox.addItem ("Alt Metal", 3);
    genreBox.addItem ("Pop-Punk", 4);
    addAndMakeVisible (genreBox);
    genreAttachment = std::make_unique<ComboAttachment> (processor.apvts, "genre", genreBox);

    auto addKnob = [this] (juce::Slider& s, const juce::String& id, bool percent = true)
    {
        setupKnob (s, percent ? "%" : "");
        sliderAttachments.push_back (std::make_unique<SliderAttachment> (processor.apvts, id, s));
    };

    addKnob (accuracy, "accuracy");
    addKnob (expression, "expression");
    addKnob (repair, "repair");
    addKnob (timing, "timingTightness");
    addKnob (humanize, "humanize");
    addKnob (mixStrength, "mixStrength");
    addKnob (stackSize, "stackSize");
    addKnob (width, "width");
    addKnob (tightness, "tightness");
    addKnob (harmony, "harmonyIntensity");
    addKnob (octaveBlend, "octaveBlend");
    addKnob (character, "character");
    addKnob (diffusion, "diffusionSteps", false);
    addKnob (identity, "identityFocus");

    statusLabel.setJustificationType (juce::Justification::centredLeft);
    statusLabel.setColour (juce::Label::textColourId, text);
    statusLabel.setFont (juce::Font (11.0f, juce::Font::plain));
    addAndMakeVisible (statusLabel);

    setPage (Page::lead);
    startTimerHz (10);
}

FORGEAudioProcessorEditor::~FORGEAudioProcessorEditor()
{
    setLookAndFeel (nullptr);
}

void FORGEAudioProcessorEditor::setupButton (juce::TextButton& b, const juce::String& t)
{
    b.setButtonText (t);
    addAndMakeVisible (b);
}

void FORGEAudioProcessorEditor::setupKnob (juce::Slider& s, const juce::String&)
{
    s.setSliderStyle (juce::Slider::RotaryHorizontalVerticalDrag);
    s.setTextBoxStyle (juce::Slider::TextBoxBelow, false, 64, 18);
    s.setColour (juce::Slider::textBoxTextColourId, text);
    s.setColour (juce::Slider::textBoxBackgroundColourId, juce::Colours::transparentBlack);
    s.setColour (juce::Slider::textBoxOutlineColourId, juce::Colours::transparentBlack);
    addAndMakeVisible (s);
}

void FORGEAudioProcessorEditor::setPage (Page p)
{
    page = p;
    captureTab.setToggleState (p == Page::capture, juce::dontSendNotification);
    leadTab.setToggleState (p == Page::lead, juce::dontSendNotification);
    stackTab.setToggleState (p == Page::stack, juce::dontSendNotification);
    neuralTab.setToggleState (p == Page::neural, juce::dontSendNotification);
    exportTab.setToggleState (p == Page::exportPage, juce::dontSendNotification);
    updateVisibility();
    resized();
    repaint();
}

void FORGEAudioProcessorEditor::updateVisibility()
{
    const bool lead = page == Page::lead;
    const bool stack = page == Page::stack;
    const bool neural = page == Page::neural;
    for (auto* s : { &accuracy, &expression, &repair, &timing, &humanize, &mixStrength }) s->setVisible (lead);
    for (auto* s : { &stackSize, &width, &tightness, &harmony, &octaveBlend, &character }) s->setVisible (stack);
    diffusion.setVisible (neural);
    identity.setVisible (neural);
    auditionProcessed.setVisible (lead);
    perfectButton.setVisible (lead);
    stackButton.setVisible (stack);
    exportFolderButton.setVisible (page == Page::exportPage);
}

void FORGEAudioProcessorEditor::timerCallback()
{
    statusLabel.setText (processor.getStatus(), juce::dontSendNotification);
    captureButton.setButtonText (processor.isCapturing() ? "Stop Capture" : "Capture Vocal");
    repaint();
}

void FORGEAudioProcessorEditor::openReferenceChooser()
{
    chooser = std::make_unique<juce::FileChooser> ("Choose reference song or vocal", juce::File(), "*.wav;*.aif;*.aiff;*.flac;*.mp3");
    chooser->launchAsync (juce::FileBrowserComponent::openMode | juce::FileBrowserComponent::canSelectFiles,
                          [this] (const juce::FileChooser& fc)
                          {
                              auto f = fc.getResult();
                              if (f.existsAsFile()) processor.setReference (f);
                          });
}

void FORGEAudioProcessorEditor::drawShell (juce::Graphics& g)
{
    g.fillAll (bg);
    auto r = getLocalBounds().toFloat().reduced (14.0f);
    auto top = r.removeFromTop (108.0f);
    panelBox (g, top);
    auto logo = top.reduced (28.0f, 18.0f).removeFromLeft (355.0f);
    g.setColour (text);
    g.setFont (juce::Font (36.0f, juce::Font::bold));
    g.drawText ("FORGE", logo.removeFromTop (45.0f), juce::Justification::centredLeft);
    g.setColour (green);
    g.setFont (juce::Font (10.0f, juce::Font::bold));
    g.drawText ("AI VOCAL PRODUCER", logo.removeFromTop (18.0f), juce::Justification::centredLeft);

    auto sidebar = r.removeFromLeft (230.0f).reduced (0.0f, 12.0f);
    panelBox (g, sidebar);
    auto s = sidebar.reduced (18.0f);
    g.setColour (muted); g.setFont (juce::Font (9.0f, juce::Font::plain));
    g.drawText ("HEAVY VOCAL WORKFLOW", s.removeFromTop (22.0f), juce::Justification::centredLeft);
    const juce::String steps[] = { "1  LOAD REFERENCE", "2  CAPTURE VOCAL", "3  AUTO KEY / ANALYZE", "4  PERFECT LEAD", "5  BUILD STACK" };
    for (auto& step : steps)
    {
        auto row = s.removeFromTop (62.0f).reduced (0.0f, 5.0f);
        g.setColour (panel2); g.fillRoundedRectangle (row, 7.0f);
        g.setColour (border); g.drawRoundedRectangle (row, 7.0f, 1.0f);
        g.setColour (text); g.setFont (juce::Font (11.0f, juce::Font::bold));
        g.drawText (step, row.reduced (12.0f), juce::Justification::centredLeft);
    }
    g.setColour (green);
    g.setFont (juce::Font (11.0f, juce::Font::bold));
    g.drawText ("VOCALS BUILT STRONGER", s.removeFromBottom (36.0f), juce::Justification::centred);
}

void FORGEAudioProcessorEditor::drawWaveform (juce::Graphics& g, juce::Rectangle<float> r, bool processed)
{
    g.setColour (juce::Colour (0xff0b1012));
    g.fillRoundedRectangle (r, 7.0f);
    g.setColour (border);
    g.drawRoundedRectangle (r, 7.0f, 1.0f);
    auto wave = processor.getDisplayWaveform (processed);
    if (wave.size() < 2) return;
    juce::Path p;
    for (size_t i = 0; i < wave.size(); ++i)
    {
        const auto x = r.getX() + r.getWidth() * (float) i / (float) (wave.size() - 1);
        const auto y = r.getCentreY() - wave[i] * r.getHeight() * 0.38f;
        if (i == 0) p.startNewSubPath (x, y); else p.lineTo (x, y);
    }
    g.setColour (processed ? green : text.withAlpha (0.65f));
    g.strokePath (p, juce::PathStrokeType (1.4f));
}

void FORGEAudioProcessorEditor::drawCapturePage (juce::Graphics& g, juce::Rectangle<float> r)
{
    panelBox (g, r);
    auto in = r.reduced (22.0f);
    title (g, in.removeFromTop (52.0f), "Capture Raw Vocal", "TRANSFER THE PERFORMANCE INTO FORGE");
    auto wave = in.removeFromTop (in.getHeight() * 0.52f);
    drawWaveform (g, wave, false);
    in.removeFromTop (16.0f);
    g.setColour (muted); g.setFont (juce::Font (13.0f));
    g.drawFittedText ("Play the vocal region in REAPER while Capture is active. FORGE stores a mono analysis copy and leaves the live signal untouched.", in.removeFromTop (70.0f), juce::Justification::centred, 3);
}

void FORGEAudioProcessorEditor::drawLeadPage (juce::Graphics& g, juce::Rectangle<float> r)
{
    panelBox (g, r);
    auto in = r.reduced (22.0f);
    title (g, in.removeFromTop (52.0f), "Vocal Performance", "EDIT  /  REFINE  /  BRING IT TO LIFE");
    auto graph = in.removeFromTop (in.getHeight() * 0.72f);
    drawWaveform (g, graph, processor.isAuditioningProcessed());
    for (int i = 1; i < 8; ++i)
    {
        g.setColour (border.withAlpha (0.45f));
        g.drawVerticalLine ((int) (graph.getX() + graph.getWidth() * (float) i / 8.0f), graph.getY(), graph.getBottom());
    }
    juce::Path pitch;
    const float n[] = { .60f,.62f,.45f,.49f,.66f,.74f,.61f,.43f,.31f,.48f,.35f,.52f,.64f };
    for (int i = 0; i < 13; ++i)
    {
        float x = graph.getX() + 20.0f + (graph.getWidth() - 40.0f) * (float) i / 12.0f;
        float y = graph.getY() + graph.getHeight() * n[i];
        if (i == 0) pitch.startNewSubPath (x, y); else pitch.lineTo (x, y);
    }
    g.setColour (green.withAlpha (0.18f)); g.strokePath (pitch, juce::PathStrokeType (10.0f));
    g.setColour (green); g.strokePath (pitch, juce::PathStrokeType (2.2f));
}

void FORGEAudioProcessorEditor::drawStackPage (juce::Graphics& g, juce::Rectangle<float> r)
{
    panelBox (g, r);
    auto in = r.reduced (22.0f);
    title (g, in.removeFromTop (52.0f), "Vocal Stack Arrangement", "LAYERS  /  HARMONIES  /  A BIGGER YOU");
    const juce::String names[] = { "Master Lead", "Double L", "Double R", "Upper Harmony", "Lower Harmony", "High Octave", "Low Octave" };
    auto lanes = in;
    const float h = lanes.getHeight() / 7.0f;
    auto wave = processor.getDisplayWaveform (true);
    for (int lane = 0; lane < 7; ++lane)
    {
        auto lr = juce::Rectangle<float> (lanes.getX(), lanes.getY() + h * lane, lanes.getWidth(), h - 4.0f);
        g.setColour ((lane % 2) ? panel2 : juce::Colour (0xff0d1214)); g.fillRoundedRectangle (lr, 5.0f);
        auto label = lr.removeFromLeft (140.0f);
        g.setColour (lane == 0 ? green : text); g.setFont (juce::Font (11.0f, juce::Font::bold));
        g.drawText (names[lane], label.reduced (10.0f), juce::Justification::centredLeft);
        if (wave.size() > 2)
        {
            juce::Path wp;
            for (size_t i = 0; i < wave.size(); ++i)
            {
                auto x = lr.getX() + lr.getWidth() * (float) i / (float) (wave.size() - 1);
                auto y = lr.getCentreY() - wave[i] * lr.getHeight() * (0.23f + lane * 0.012f);
                if (i == 0) wp.startNewSubPath (x, y); else wp.lineTo (x, y);
            }
            g.setColour ((lane >= 3 ? green : text).withAlpha (lane == 0 ? 0.9f : 0.45f));
            g.strokePath (wp, juce::PathStrokeType (1.0f));
        }
    }
}

void FORGEAudioProcessorEditor::drawNeuralPage (juce::Graphics& g, juce::Rectangle<float> r)
{
    panelBox (g, r);
    auto in = r.reduced (22.0f);
    title (g, in.removeFromTop (52.0f), "Neural Voice Cloning", "CAPTURE  /  TEST  /  VERIFY  /  RENDER");
    auto cards = in.removeFromTop (180.0f);
    const juce::String labels[] = { "1  Target Voice", "2  Guide Performance", "3  Candidate Test", "4  QA Results", "5  Full Render Lock" };
    for (int i = 0; i < 5; ++i)
    {
        auto c = cards.removeFromLeft (cards.getWidth() / (5 - i)).reduced (5.0f);
        g.setColour (panel2); g.fillRoundedRectangle (c, 7.0f);
        g.setColour (border); g.drawRoundedRectangle (c, 7.0f, 1.0f);
        g.setColour (i < 3 ? green : muted); g.setFont (juce::Font (12.0f, juce::Font::bold));
        g.drawFittedText (labels[i], c.reduced (10.0f), juce::Justification::centred, 2);
    }
    in.removeFromTop (18.0f);
    auto qa = in;
    g.setColour (panel2); g.fillRoundedRectangle (qa, 7.0f);
    g.setColour (border); g.drawRoundedRectangle (qa, 7.0f, 1.0f);
    g.setColour (amber); g.setFont (juce::Font (14.0f, juce::Font::bold));
    g.drawText ("NEURAL FULL-SONG EXPORT LOCKED UNTIL TORTURE TEST PASSES", qa.reduced (18.0f), juce::Justification::centred);
}

void FORGEAudioProcessorEditor::drawExportPage (juce::Graphics& g, juce::Rectangle<float> r)
{
    panelBox (g, r);
    auto in = r.reduced (22.0f);
    title (g, in.removeFromTop (52.0f), "Export", "READY-TO-MIX STEMS");
    const juce::String files[] = { "01  Perfect Lead Dry", "02  Master Lead Mixed", "03  Double L", "04  Double R", "05  Upper Harmony", "06  Lower Harmony", "07  High Octave", "08  Low Octave", "09  Stack Reference Mix" };
    for (auto& f : files)
    {
        auto row = in.removeFromTop (46.0f).reduced (0.0f, 3.0f);
        g.setColour (panel2); g.fillRoundedRectangle (row, 5.0f);
        g.setColour (green); g.fillEllipse (row.getX() + 10.0f, row.getCentreY() - 4.0f, 8.0f, 8.0f);
        g.setColour (text); g.setFont (juce::Font (11.0f));
        g.drawText (f, row.withTrimmedLeft (28.0f), juce::Justification::centredLeft);
    }
}

void FORGEAudioProcessorEditor::paint (juce::Graphics& g)
{
    drawShell (g);
    auto r = getLocalBounds().toFloat().reduced (14.0f);
    r.removeFromTop (108.0f);
    r.removeFromLeft (230.0f);
    r = r.reduced (12.0f);
    r.removeFromRight (310.0f);
    switch (page)
    {
        case Page::capture: drawCapturePage (g, r); break;
        case Page::lead: drawLeadPage (g, r); break;
        case Page::stack: drawStackPage (g, r); break;
        case Page::neural: drawNeuralPage (g, r); break;
        case Page::exportPage: drawExportPage (g, r); break;
    }

    auto right = getLocalBounds().toFloat().reduced (14.0f);
    right.removeFromTop (120.0f);
    right = right.removeFromRight (298.0f).reduced (4.0f);
    panelBox (g, right);
    auto q = right.reduced (16.0f);
    g.setColour (text); g.setFont (juce::Font (17.0f, juce::Font::bold));
    g.drawText (page == Page::stack ? "Stack Controls" : page == Page::neural ? "Neural Controls" : "Lead Controls", q.removeFromTop (28.0f), juce::Justification::centredLeft);
    if (page == Page::lead)
    {
        const juce::String names[] = { "Accuracy", "Expression", "Repair", "Timing", "Humanize", "Mix Strength" };
        for (int i = 0; i < 6; ++i) { g.setColour (muted); g.setFont (juce::Font (10.0f)); g.drawText (names[i], q.removeFromTop (100.0f), juce::Justification::centredLeft); }
    }
    else if (page == Page::stack)
    {
        const juce::String names[] = { "Stack Size", "Width", "Tightness", "Harmony", "Octave Blend", "Character" };
        for (int i = 0; i < 6; ++i) { g.setColour (muted); g.setFont (juce::Font (10.0f)); g.drawText (names[i], q.removeFromTop (100.0f), juce::Justification::centredLeft); }
    }
}

void FORGEAudioProcessorEditor::resized()
{
    auto r = getLocalBounds().reduced (14);
    auto top = r.removeFromTop (108);
    auto tabs = top.reduced (420, 18);
    tabs.removeFromRight (40);
    const int tw = juce::jmax (90, tabs.getWidth() / 5);
    captureTab.setBounds (tabs.removeFromLeft (tw).reduced (4));
    leadTab.setBounds (tabs.removeFromLeft (tw).reduced (4));
    stackTab.setBounds (tabs.removeFromLeft (tw).reduced (4));
    neuralTab.setBounds (tabs.removeFromLeft (tw).reduced (4));
    exportTab.setBounds (tabs.removeFromLeft (tw).reduced (4));

    auto sidebar = r.removeFromLeft (230).reduced (18, 22);
    sidebar.removeFromTop (340);
    loadReferenceButton.setBounds (sidebar.removeFromTop (44).reduced (0, 3));
    captureButton.setBounds (sidebar.removeFromTop (44).reduced (0, 3));
    genreBox.setBounds (sidebar.removeFromTop (40).reduced (0, 3));
    produceButton.setBounds (sidebar.removeFromTop (64).reduced (0, 7));

    auto right = r.removeFromRight (310).reduced (16, 24);
    right.removeFromTop (42);
    auto layoutSix = [&right] (std::initializer_list<juce::Slider*> ss)
    {
        for (auto* s : ss) s->setBounds (right.removeFromTop (100).reduced (120, 4, 4, 4));
    };
    if (page == Page::lead)
    {
        layoutSix ({ &accuracy, &expression, &repair, &timing, &humanize, &mixStrength });
        auditionProcessed.setBounds (right.removeFromTop (36));
        perfectButton.setBounds (right.removeFromTop (48).reduced (0, 4));
    }
    else if (page == Page::stack)
    {
        layoutSix ({ &stackSize, &width, &tightness, &harmony, &octaveBlend, &character });
        stackButton.setBounds (right.removeFromTop (48).reduced (0, 4));
    }
    else if (page == Page::neural)
    {
        diffusion.setBounds (right.removeFromTop (110).reduced (120, 6, 4, 6));
        identity.setBounds (right.removeFromTop (110).reduced (120, 6, 4, 6));
    }
    else if (page == Page::exportPage)
    {
        exportFolderButton.setBounds (right.removeFromTop (50).reduced (0, 4));
    }

    auto status = getLocalBounds().reduced (28);
    status.removeFromTop (getHeight() - 58);
    statusLabel.setBounds (status);
}
