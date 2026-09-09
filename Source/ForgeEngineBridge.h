#pragma once
#include <JuceHeader.h>

class ForgeEngineBridge
{
public:
    ForgeEngineBridge();

    void setProjectRoot (juce::File root);
    void setSessionId (juce::String id) { sessionId = std::move (id); }
    juce::String getSessionId() const { return sessionId; }
    void setReferenceFile (juce::File file) { referenceFile = std::move (file); }
    juce::File getReferenceFile() const { return referenceFile; }

    juce::File getSessionDir() const;
    juce::File getEngineExecutable() const;
    juce::File getEngineScript() const;
    juce::File getPython() const;

    bool runPerfectLead (const juce::File& input,
                         const juce::File& outputDry,
                         const juce::File& outputMixed,
                         juce::String genre,
                         float accuracy,
                         float expression,
                         float repair,
                         float timingTightness,
                         float humanize,
                         float mixStrength,
                         juce::String& log);

    bool runBuildStack (const juce::File& input,
                        const juce::File& outputDirectory,
                        juce::String genre,
                        bool hostedNeural,
                        float stackSize,
                        float width,
                        float tightness,
                        float harmonyIntensity,
                        float octaveBlend,
                        float character,
                        int diffusionSteps,
                        float identityFocus,
                        juce::String& log);

private:
    bool launchEngine (juce::StringArray engineArgs, juce::String& log) const;
    juce::File getModuleFile() const;

    juce::File projectRoot;
    juce::File referenceFile;
    juce::String sessionId { "default" };
};
