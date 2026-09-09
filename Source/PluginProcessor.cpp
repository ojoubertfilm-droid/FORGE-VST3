#include "PluginProcessor.h"
#include <cmath>
#include "PluginEditor.h"

FORGEAudioProcessor::FORGEAudioProcessor()
    : AudioProcessor (BusesProperties().withInput ("Input", juce::AudioChannelSet::stereo(), true)
                                      .withOutput ("Output", juce::AudioChannelSet::stereo(), true)),
      apvts (*this, nullptr, "FORGE_STATE", createLayout())
{
#if JUCE_WINDOWS
    appRoot = juce::File::getSpecialLocation (juce::File::userApplicationDataDirectory)
                  .getChildFile ("OJ Labs").getChildFile ("FORGE");
#else
    appRoot = juce::File::getSpecialLocation (juce::File::userApplicationDataDirectory).getChildFile ("FORGE");
#endif
    appRoot.createDirectory();
    sessionId = juce::Uuid().toString();
    engine.setProjectRoot (appRoot);
    engine.setSessionId (sessionId);
    refreshSessionFiles();
    startTimerHz (5);
}

FORGEAudioProcessor::~FORGEAudioProcessor() = default;

juce::AudioProcessorValueTreeState::ParameterLayout FORGEAudioProcessor::createLayout()
{
    juce::AudioProcessorValueTreeState::ParameterLayout p;
    p.add (std::make_unique<juce::AudioParameterChoice> ("genre", "Genre",
            juce::StringArray { "Modern Metalcore", "Post-Hardcore", "Alt Metal", "Pop-Punk" }, 0));
    p.add (std::make_unique<juce::AudioParameterFloat> ("accuracy", "Accuracy", 0.0f, 1.0f, 0.86f));
    p.add (std::make_unique<juce::AudioParameterFloat> ("expression", "Expression", 0.0f, 1.0f, 0.70f));
    p.add (std::make_unique<juce::AudioParameterFloat> ("repair", "Repair", 0.0f, 1.0f, 0.62f));
    p.add (std::make_unique<juce::AudioParameterFloat> ("timingTightness", "Timing Tightness", 0.0f, 1.0f, 0.68f));
    p.add (std::make_unique<juce::AudioParameterFloat> ("humanize", "Humanize", 0.0f, 1.0f, 0.70f));
    p.add (std::make_unique<juce::AudioParameterFloat> ("mixStrength", "Mix Strength", 0.0f, 1.0f, 0.82f));
    p.add (std::make_unique<juce::AudioParameterFloat> ("stackSize", "Stack Size", 0.0f, 1.0f, 0.78f));
    p.add (std::make_unique<juce::AudioParameterFloat> ("width", "Width", 0.0f, 1.0f, 0.82f));
    p.add (std::make_unique<juce::AudioParameterFloat> ("tightness", "Stack Tightness", 0.0f, 1.0f, 0.72f));
    p.add (std::make_unique<juce::AudioParameterFloat> ("harmonyIntensity", "Harmony Intensity", 0.0f, 1.0f, 0.74f));
    p.add (std::make_unique<juce::AudioParameterFloat> ("octaveBlend", "Octave Blend", 0.0f, 1.0f, 0.52f));
    p.add (std::make_unique<juce::AudioParameterFloat> ("character", "Character", 0.0f, 1.0f, 0.66f));
    p.add (std::make_unique<juce::AudioParameterFloat> ("diffusionSteps", "Diffusion Steps",
             juce::NormalisableRange<float> (30.0f, 100.0f, 1.0f), 50.0f));
    p.add (std::make_unique<juce::AudioParameterFloat> ("identityFocus", "Identity Focus", 0.0f, 1.0f, 0.70f));
    return p;
}

void FORGEAudioProcessor::refreshSessionFiles()
{
    engine.setSessionId (sessionId);
    auto d = engine.getSessionDir();
    captureFile = d.getChildFile ("capture.wav");
    processedFile = d.getChildFile ("perfect_lead_dry.wav");
    mixedFile = d.getChildFile ("mixed_lead.wav");
}

juce::String FORGEAudioProcessor::getGenreSlug() const
{
    const int idx = (int) std::round (apvts.getRawParameterValue ("genre")->load());
    switch (idx)
    {
        case 1: return "post_hardcore";
        case 2: return "alt_metal";
        case 3: return "pop_punk";
        default: return "modern_metalcore";
    }
}

void FORGEAudioProcessor::prepareToPlay (double sr, int)
{
    currentSampleRate = sr;
    captureBuffer.setSize (1, (int) (sr * 60.0 * 5.0), false, true, false);
    captureBuffer.clear();
}

void FORGEAudioProcessor::releaseResources() {}

bool FORGEAudioProcessor::isBusesLayoutSupported (const BusesLayout& l) const
{
    const auto in = l.getMainInputChannelSet();
    const auto out = l.getMainOutputChannelSet();
    if (out != juce::AudioChannelSet::mono() && out != juce::AudioChannelSet::stereo()) return false;
    return in == out;
}

void FORGEAudioProcessor::processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer&)
{
    juce::ScopedNoDenormals nd;
    auto pos = getPlayHead() != nullptr ? getPlayHead()->getPosition() : std::optional<juce::AudioPlayHead::PositionInfo>();
    juce::int64 hostSample = pos && pos->getTimeInSamples() ? *pos->getTimeInSamples() : 0;

    if (capturing.load (std::memory_order_acquire))
    {
        const auto n = buffer.getNumSamples();
        const auto start = capturedSamples.load (std::memory_order_relaxed);
        if (start + n < captureBuffer.getNumSamples())
        {
            for (int i = 0; i < n; ++i)
            {
                float v = 0.0f;
                for (int ch = 0; ch < buffer.getNumChannels(); ++ch) v += buffer.getSample (ch, i);
                v /= juce::jmax (1, buffer.getNumChannels());
                captureBuffer.setSample (0, (int) start + i, v);
            }
            capturedSamples.store (start + n, std::memory_order_release);
        }
    }

    if (auditionProcessed.load (std::memory_order_acquire))
    {
        auto snapshot = processedBuffer.load (std::memory_order_acquire);
        if (snapshot != nullptr && snapshot->getNumSamples() > 0)
        {
            const auto offset = hostSample - processedHostStart;
            if (offset >= 0 && offset < snapshot->getNumSamples())
            {
                auto count = juce::jmin<juce::int64> (buffer.getNumSamples(), snapshot->getNumSamples() - offset);
                buffer.clear();
                for (int ch = 0; ch < buffer.getNumChannels(); ++ch)
                    buffer.copyFrom (ch, 0, *snapshot, 0, (int) offset, (int) count);
            }
        }
    }

    float peak = 0.0f;
    for (int ch = 0; ch < buffer.getNumChannels(); ++ch)
        peak = juce::jmax (peak, buffer.getMagnitude (ch, 0, buffer.getNumSamples()));
    const float old = outputLevel.load();
    outputLevel.store (peak > old ? peak : old * 0.88f);
}

void FORGEAudioProcessor::toggleCapture()
{
    const bool wasCapturing = capturing.load();
    if (! wasCapturing)
    {
        captureBuffer.clear();
        capturedSamples.store (0, std::memory_order_release);
        auto pos = getPlayHead() != nullptr ? getPlayHead()->getPosition() : std::optional<juce::AudioPlayHead::PositionInfo>();
        captureHostStart = pos && pos->getTimeInSamples() ? *pos->getTimeInSamples() : 0;
        capturing.store (true, std::memory_order_release);
        setStatus ("Capturing raw vocal... play the region, then press Stop Capture.");
    }
    else
    {
        capturing.store (false, std::memory_order_release);
        processedHostStart = captureHostStart;
        juce::Timer::callAfterDelay (60, [this] { writeCapturedAudioAsync(); });
    }
}

void FORGEAudioProcessor::writeCapturedAudioAsync()
{
    setStatus ("Writing captured vocal...");
    juce::AudioBuffer<float> copy;
    const auto count = capturedSamples.load (std::memory_order_acquire);
    copy.setSize (1, (int) count, false, true, false);
    if (count > 0) copy.copyFrom (0, 0, captureBuffer, 0, 0, (int) count);
    auto f = captureFile;
    auto sr = currentSampleRate;
    juce::Thread::launch ([this, copy = std::move (copy), f, sr]() mutable
    {
        f.deleteFile();
        juce::WavAudioFormat wav;
        if (auto stream = std::unique_ptr<juce::FileOutputStream> (f.createOutputStream()))
        {
            if (auto writer = std::unique_ptr<juce::AudioFormatWriter> (wav.createWriterFor (stream.release(), sr, 1, 24, {}, 0)))
                writer->writeFromAudioSampleBuffer (copy, 0, copy.getNumSamples());
        }
        setStatus ("Raw vocal captured. Load a reference and press Produce Vocal.");
    });
}

void FORGEAudioProcessor::setReference (const juce::File& f)
{
    engine.setReferenceFile (f);
    setStatus ("Reference loaded: " + f.getFileName());
}

void FORGEAudioProcessor::perfectLead()
{
    if (engineBusy.exchange (true)) return;
    if (! captureFile.existsAsFile()) { engineBusy.store (false); setStatus ("Capture a raw vocal first."); return; }
    setStatus ("FORGE is finding the key and producing the lead...");
    auto genre = getGenreSlug();
    auto accuracy = apvts.getRawParameterValue("accuracy")->load();
    auto expression = apvts.getRawParameterValue("expression")->load();
    auto repair = apvts.getRawParameterValue("repair")->load();
    auto timing = apvts.getRawParameterValue("timingTightness")->load();
    auto humanize = apvts.getRawParameterValue("humanize")->load();
    auto mixStrength = apvts.getRawParameterValue("mixStrength")->load();
    juce::Thread::launch ([this, genre, accuracy, expression, repair, timing, humanize, mixStrength]
    {
        juce::String log;
        auto ok = engine.runPerfectLead (captureFile, processedFile, mixedFile, genre, accuracy, expression, repair, timing, humanize, mixStrength, log);
        if (ok)
        {
            loadProcessedAudio();
            auto first = log.upToFirstOccurrenceOf("\n", false, false).replace("FORGE_KEY=", "Key: ").replace("|CONF=", " - confidence ").replace("|PROTECTED=", " - protected rough events ").replace("|EVENTS=", " - notes ");
            setStatus ("Mixed Lead ready - " + first);
        }
        else setStatus ("Engine failed: " + log.substring (0, 240));
        engineBusy.store (false);
    });
}

void FORGEAudioProcessor::buildStack (bool hostedNeural)
{
    if (engineBusy.exchange (true)) return;
    auto input = processedFile.existsAsFile() ? processedFile : captureFile;
    if (! input.existsAsFile()) { engineBusy.store (false); setStatus ("Create a lead first."); return; }
    auto out = getExportDir();
    auto genre = getGenreSlug();
    auto stackSize = apvts.getRawParameterValue("stackSize")->load();
    auto width = apvts.getRawParameterValue("width")->load();
    auto tightness = apvts.getRawParameterValue("tightness")->load();
    auto harmony = apvts.getRawParameterValue("harmonyIntensity")->load();
    auto octave = apvts.getRawParameterValue("octaveBlend")->load();
    auto character = apvts.getRawParameterValue("character")->load();
    auto diffusion = apvts.getRawParameterValue("diffusionSteps")->load();
    auto identity = apvts.getRawParameterValue("identityFocus")->load();
    setStatus (hostedNeural ? "Building neural heavy-vocal stack..." : "Building harmony / double reference stack...");
    juce::Thread::launch ([this, input, out, genre, hostedNeural, stackSize, width, tightness, harmony, octave, character, diffusion, identity]
    {
        juce::String log;
        auto ok = engine.runBuildStack (input, out, genre, hostedNeural, stackSize, width, tightness, harmony, octave, character, (int) std::round (diffusion), identity, log);
        if (ok) writeLatestExportMarker (out);
        setStatus (ok ? "Stack ready: dry lead, mixed lead, doubles, harmonies, octaves + reference mix." : "Stack failed: " + log.substring (0, 240));
        engineBusy.store (false);
    });
}

void FORGEAudioProcessor::produceVocal()
{
    if (engineBusy.exchange (true)) return;
    if (! captureFile.existsAsFile()) { engineBusy.store (false); setStatus ("Capture a raw vocal first."); return; }
    auto out = getExportDir(); auto genre = getGenreSlug();
    auto accuracy = apvts.getRawParameterValue("accuracy")->load();
    auto expression = apvts.getRawParameterValue("expression")->load();
    auto repair = apvts.getRawParameterValue("repair")->load();
    auto timing = apvts.getRawParameterValue("timingTightness")->load();
    auto humanize = apvts.getRawParameterValue("humanize")->load();
    auto mixStrength = apvts.getRawParameterValue("mixStrength")->load();
    auto stackSize = apvts.getRawParameterValue("stackSize")->load();
    auto width = apvts.getRawParameterValue("width")->load();
    auto tightness = apvts.getRawParameterValue("tightness")->load();
    auto harmony = apvts.getRawParameterValue("harmonyIntensity")->load();
    auto octave = apvts.getRawParameterValue("octaveBlend")->load();
    auto character = apvts.getRawParameterValue("character")->load();
    auto diffusion = apvts.getRawParameterValue("diffusionSteps")->load();
    auto identity = apvts.getRawParameterValue("identityFocus")->load();
    setStatus ("Producing vocal: key -> tune -> mix -> stack...");
    juce::Thread::launch ([this, out, genre, accuracy, expression, repair, timing, humanize, mixStrength, stackSize, width, tightness, harmony, octave, character, diffusion, identity]
    {
        juce::String leadLog, stackLog;
        auto leadOK = engine.runPerfectLead (captureFile, processedFile, mixedFile, genre, accuracy, expression, repair, timing, humanize, mixStrength, leadLog);
        if (! leadOK) { setStatus ("Lead stage failed: " + leadLog.substring (0, 240)); engineBusy.store (false); return; }
        loadProcessedAudio();
        auto stackOK = engine.runBuildStack (processedFile, out, genre, false, stackSize, width, tightness, harmony, octave, character, (int) std::round (diffusion), identity, stackLog);
        if (stackOK)
        {
            writeLatestExportMarker (out);
            auto first = leadLog.upToFirstOccurrenceOf("\n", false, false).replace("FORGE_KEY=", "Key: ").replace("|CONF=", " - confidence ").replace("|PROTECTED=", " - rough protected ").replace("|EVENTS=", " - pitched events ");
            setStatus ("FORGE Vocal ready - " + first + " - exports ready");
        }
        else setStatus ("Lead ready, but stack failed: " + stackLog.substring (0, 200));
        engineBusy.store (false);
    });
}

void FORGEAudioProcessor::loadProcessedAudio()
{
    auto target = mixedFile.existsAsFile() ? mixedFile : processedFile;
    juce::AudioFormatManager fm; fm.registerBasicFormats();
    if (auto r = std::unique_ptr<juce::AudioFormatReader> (fm.createReaderFor (target)))
    {
        auto temp = std::make_shared<juce::AudioBuffer<float>> (1, (int) r->lengthInSamples);
        r->read (temp.get(), 0, temp->getNumSamples(), 0, true, false);
        processedBuffer.store (std::move (temp), std::memory_order_release);
    }
}

std::vector<float> FORGEAudioProcessor::getDisplayWaveform (bool preferProcessed) const
{
    constexpr int points = 320;
    std::vector<float> out (points, 0.0f);
    juce::AudioBuffer<float> temp;
    if (preferProcessed)
    {
        auto snapshot = processedBuffer.load (std::memory_order_acquire);
        if (snapshot != nullptr && snapshot->getNumSamples() > 0) temp.makeCopyOf (*snapshot);
    }
    if (temp.getNumSamples() == 0 && ! capturing.load (std::memory_order_acquire))
    {
        const auto count = capturedSamples.load (std::memory_order_acquire);
        if (count > 0)
        {
            temp.setSize (1, (int) count);
            temp.copyFrom (0, 0, captureBuffer, 0, 0, (int) count);
        }
    }
    if (temp.getNumSamples() <= 0) return out;
    const auto n = temp.getNumSamples();
    for (int i = 0; i < points; ++i)
    {
        auto a = (int) ((juce::int64) i * n / points);
        auto b = (int) ((juce::int64) (i + 1) * n / points);
        b = juce::jmax (a + 1, juce::jmin (b, n));
        float mx = 0.0f, signedPeak = 0.0f;
        for (int j = a; j < b; ++j) { auto v = temp.getSample (0, j); if (std::abs (v) > mx) { mx = std::abs (v); signedPeak = v; } }
        out[(size_t) i] = juce::jlimit (-1.0f, 1.0f, signedPeak * 8.0f);
    }
    return out;
}

juce::File FORGEAudioProcessor::getExportDir() const
{
    auto d = juce::File::getSpecialLocation (juce::File::userMusicDirectory).getChildFile ("FORGE Exports").getChildFile (sessionId);
    d.createDirectory();
    return d;
}

void FORGEAudioProcessor::writeLatestExportMarker (const juce::File& exportDir)
{
    auto marker = appRoot.getChildFile ("latest_export.txt");
    const auto startSeconds = currentSampleRate > 0.0 ? (double) processedHostStart / currentSampleRate : 0.0;
    marker.replaceWithText (exportDir.getFullPathName() + "\n" + juce::String (startSeconds, 9) + "\n");
}

juce::String FORGEAudioProcessor::getStatus() const { const juce::ScopedLock sl (statusLock); return status; }
void FORGEAudioProcessor::setStatus (juce::String s) { const juce::ScopedLock sl (statusLock); status = std::move (s); }
void FORGEAudioProcessor::timerCallback() {}

void FORGEAudioProcessor::getStateInformation (juce::MemoryBlock& dest)
{
    auto state = apvts.copyState();
    state.setProperty ("reference", engine.getReferenceFile().getFullPathName(), nullptr);
    state.setProperty ("sessionId", sessionId, nullptr);
    state.setProperty ("processedHostStart", processedHostStart, nullptr);
    if (auto xml = state.createXml()) copyXmlToBinary (*xml, dest);
}

void FORGEAudioProcessor::setStateInformation (const void* data, int size)
{
    if (auto xml = getXmlFromBinary (data, size))
        if (xml->hasTagName (apvts.state.getType()))
        {
            auto restored = juce::ValueTree::fromXml (*xml); apvts.replaceState (restored);
            auto sid = apvts.state.getProperty ("sessionId").toString(); if (sid.isNotEmpty()) sessionId = sid;
            engine.setSessionId (sessionId); refreshSessionFiles();
            auto ref = apvts.state.getProperty ("reference").toString(); if (ref.isNotEmpty()) engine.setReferenceFile (juce::File (ref));
            processedHostStart = (juce::int64) apvts.state.getProperty ("processedHostStart", 0);
            if (mixedFile.existsAsFile() || processedFile.existsAsFile()) loadProcessedAudio();
        }
}

juce::AudioProcessorEditor* FORGEAudioProcessor::createEditor() { return new FORGEAudioProcessorEditor (*this); }
juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter() { return new FORGEAudioProcessor(); }
