#pragma once
#include <JuceHeader.h>
#include "PluginProcessor.h"

class ForgeLookAndFeel final : public juce::LookAndFeel_V4
{
public:
    ForgeLookAndFeel();
    void drawButtonBackground (juce::Graphics&, juce::Button&, const juce::Colour&, bool, bool) override;
    void drawButtonText (juce::Graphics&, juce::TextButton&, bool, bool) override;
    void drawRotarySlider (juce::Graphics&, int, int, int, int, float, float, float, juce::Slider&) override;
};

class FORGEAudioProcessorEditor final : public juce::AudioProcessorEditor,
                                        private juce::Timer
{
public:
    explicit FORGEAudioProcessorEditor (FORGEAudioProcessor&);
    ~FORGEAudioProcessorEditor() override;

    void paint (juce::Graphics&) override;
    void resized() override;

private:
    enum class Page { capture, lead, stack, neural, exportPage };

    void timerCallback() override;
    void setPage (Page);
    void setupKnob (juce::Slider&, const juce::String& suffix = "%");
    void setupButton (juce::TextButton&, const juce::String& text);
    void drawShell (juce::Graphics&);
    void drawCapturePage (juce::Graphics&, juce::Rectangle<float>);
    void drawLeadPage (juce::Graphics&, juce::Rectangle<float>);
    void drawStackPage (juce::Graphics&, juce::Rectangle<float>);
    void drawNeuralPage (juce::Graphics&, juce::Rectangle<float>);
    void drawExportPage (juce::Graphics&, juce::Rectangle<float>);
    void drawWaveform (juce::Graphics&, juce::Rectangle<float>, bool processed);
    void openReferenceChooser();
    void updateVisibility();

    FORGEAudioProcessor& processor;
    ForgeLookAndFeel forgeLaf;
    Page page { Page::lead };

    juce::TextButton captureTab, leadTab, stackTab, neuralTab, exportTab;
    juce::TextButton loadReferenceButton, captureButton, produceButton;
    juce::TextButton perfectButton, stackButton, exportFolderButton;
    juce::ToggleButton auditionProcessed { "Processed" };
    juce::ComboBox genreBox;

    juce::Slider accuracy, expression, repair, timing, humanize, mixStrength;
    juce::Slider stackSize, width, tightness, harmony, octaveBlend, character;
    juce::Slider diffusion, identity;

    using SliderAttachment = juce::AudioProcessorValueTreeState::SliderAttachment;
    using ComboAttachment = juce::AudioProcessorValueTreeState::ComboBoxAttachment;
    std::vector<std::unique_ptr<SliderAttachment>> sliderAttachments;
    std::unique_ptr<ComboAttachment> genreAttachment;
    std::unique_ptr<juce::FileChooser> chooser;

    juce::Label statusLabel;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (FORGEAudioProcessorEditor)
};
