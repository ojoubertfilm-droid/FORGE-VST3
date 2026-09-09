#pragma once
#include <JuceHeader.h>
#include <atomic>
#include <memory>
#include "ForgeEngineBridge.h"

class FORGEAudioProcessor : public juce::AudioProcessor,
                            private juce::Timer
{
public:
    FORGEAudioProcessor();
    ~FORGEAudioProcessor() override;

    void prepareToPlay (double sampleRate, int samplesPerBlock) override;
    void releaseResources() override;
    bool isBusesLayoutSupported (const BusesLayout&) const override;
    void processBlock (juce::AudioBuffer<float>&, juce::MidiBuffer&) override;

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override { return true; }
    const juce::String getName() const override { return JucePlugin_Name; }
    bool acceptsMidi() const override { return false; }
    bool producesMidi() const override { return false; }
    bool isMidiEffect() const override { return false; }
    double getTailLengthSeconds() const override { return 0.0; }
    int getNumPrograms() override { return 1; }
    int getCurrentProgram() override { return 0; }
    void setCurrentProgram (int) override {}
    const juce::String getProgramName (int) override { return {}; }
    void changeProgramName (int, const juce::String&) override {}
    void getStateInformation (juce::MemoryBlock&) override;
    void setStateInformation (const void*, int) override;

    void toggleCapture();
    bool isCapturing() const noexcept { return capturing.load(); }
    void setReference (const juce::File& f);
    juce::File getReference() const { return engine.getReferenceFile(); }
    void perfectLead();
    void buildStack (bool hostedNeural);
    void produceVocal();
    void setAuditionProcessed (bool b) { auditionProcessed.store (b); }
    bool isAuditioningProcessed() const { return auditionProcessed.load(); }
    juce::String getStatus() const;
    juce::File getExportDir() const;
    float getOutputLevel() const noexcept { return outputLevel.load(); }
    std::vector<float> getDisplayWaveform (bool preferProcessed) const;
    void setStatusFromUI (juce::String s) { setStatus (std::move (s)); }

    juce::AudioProcessorValueTreeState apvts;

private:
    static juce::AudioProcessorValueTreeState::ParameterLayout createLayout();
    void timerCallback() override;
    void writeCapturedAudioAsync();
    void loadProcessedAudio();
    void setStatus (juce::String s);
    juce::String getGenreSlug() const;
    void refreshSessionFiles();
    void writeLatestExportMarker (const juce::File& exportDir);

    ForgeEngineBridge engine;
    juce::File appRoot, captureFile, processedFile, mixedFile;
    juce::String sessionId;

    std::atomic<bool> capturing { false };
    std::atomic<bool> auditionProcessed { true };
    std::atomic<bool> engineBusy { false };
    std::atomic<float> outputLevel { 0.0f };

    juce::AudioBuffer<float> captureBuffer;
    std::atomic<juce::int64> capturedSamples { 0 };
    juce::int64 captureHostStart = 0;

    std::atomic<std::shared_ptr<juce::AudioBuffer<float>>> processedBuffer;
    juce::int64 processedHostStart = 0;

    mutable juce::CriticalSection statusLock;
    juce::String status { "Ready" };
    double currentSampleRate = 44100.0;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (FORGEAudioProcessor)
};
