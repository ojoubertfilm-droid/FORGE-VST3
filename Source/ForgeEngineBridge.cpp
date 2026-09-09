#include "ForgeEngineBridge.h"
#include <cstdlib>

#if JUCE_WINDOWS
 #include <windows.h>
 namespace { void forgeModuleAnchor() {} }
#endif

ForgeEngineBridge::ForgeEngineBridge()
{
#if JUCE_WINDOWS
    projectRoot = juce::File::getSpecialLocation (juce::File::userApplicationDataDirectory)
                    .getChildFile ("OJ Labs").getChildFile ("FORGE");
#else
    projectRoot = juce::File::getSpecialLocation (juce::File::userApplicationDataDirectory).getChildFile ("FORGE");
#endif
    projectRoot.createDirectory();
}

void ForgeEngineBridge::setProjectRoot (juce::File root)
{
    projectRoot = std::move (root);
    projectRoot.createDirectory();
}

juce::File ForgeEngineBridge::getModuleFile() const
{
#if JUCE_WINDOWS
    HMODULE module = nullptr;
    if (GetModuleHandleExW (GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                            reinterpret_cast<LPCWSTR> (&forgeModuleAnchor), &module) != 0)
    {
        std::wstring buffer (32768, L'\0');
        const auto length = GetModuleFileNameW (module, buffer.data(), static_cast<DWORD> (buffer.size()));
        if (length > 0)
            return juce::File (juce::String (buffer.data(), static_cast<int> (length)));
    }
#endif
    return juce::File::getSpecialLocation (juce::File::currentExecutableFile);
}

juce::File ForgeEngineBridge::getEngineExecutable() const
{
#if JUCE_WINDOWS
    const auto module = getModuleFile();
    auto dir = module.getParentDirectory();
    if (dir.getFileName().containsIgnoreCase ("-win"))
    {
        auto bundled = dir.getParentDirectory().getChildFile ("Resources").getChildFile ("Engine").getChildFile ("forge_engine.exe");
        if (bundled.existsAsFile()) return bundled;
    }
    auto besideStandalone = dir.getChildFile ("Engine").getChildFile ("forge_engine.exe");
    if (besideStandalone.existsAsFile()) return besideStandalone;
#endif
    return {};
}

juce::File ForgeEngineBridge::getPython() const
{
#if JUCE_WINDOWS
    auto venvPython = projectRoot.getChildFile ("venv").getChildFile ("Scripts").getChildFile ("python.exe");
    if (venvPython.existsAsFile()) return venvPython;
    return juce::File ("python.exe");
#else
    return juce::File ("python3");
#endif
}

juce::File ForgeEngineBridge::getEngineScript() const
{
    auto local = projectRoot.getChildFile ("Engine").getChildFile ("forge_engine.py");
    if (local.existsAsFile()) return local;
#if JUCE_WINDOWS
    const auto module = getModuleFile();
    auto dir = module.getParentDirectory();
    if (dir.getFileName().containsIgnoreCase ("-win"))
    {
        auto bundled = dir.getParentDirectory().getChildFile ("Resources").getChildFile ("Engine").getChildFile ("forge_engine.py");
        if (bundled.existsAsFile()) return bundled;
    }
#endif
    return local;
}

juce::File ForgeEngineBridge::getSessionDir() const
{
    auto safe = sessionId.isNotEmpty() ? sessionId : juce::String ("default");
    auto d = projectRoot.getChildFile ("Sessions").getChildFile (safe);
    d.createDirectory();
    return d;
}

bool ForgeEngineBridge::launchEngine (juce::StringArray engineArgs, juce::String& log) const
{
    juce::StringArray command;
#if JUCE_WINDOWS
    auto exe = getEngineExecutable();
    if (exe.existsAsFile())
    {
        command.add (exe.getFullPathName());
        command.addArray (engineArgs);
    }
    else
#endif
    {
        auto script = getEngineScript();
        if (! script.existsAsFile())
        {
            log = "FORGE engine is missing. Reinstall FORGE.";
            return false;
        }
        command.add (getPython().getFullPathName());
        command.add (script.getFullPathName());
        command.addArray (engineArgs);
    }

    juce::ChildProcess proc;
    if (! proc.start (command))
    {
        log = "Could not start FORGE offline engine.";
        return false;
    }
    if (! proc.waitForProcessToFinish (10 * 60 * 1000))
    {
        proc.kill();
        log = "FORGE engine timed out.";
        return false;
    }
    log = proc.readAllProcessOutput();
    return proc.getExitCode() == 0;
}

bool ForgeEngineBridge::runPerfectLead (const juce::File& input,
                                        const juce::File& outputDry,
                                        const juce::File& outputMixed,
                                        juce::String genre,
                                        float accuracy, float expression, float repair,
                                        float timingTightness, float humanize, float mixStrength,
                                        juce::String& log)
{
    juce::StringArray args { "perfect-lead", "--input", input.getFullPathName(),
                             "--output", outputDry.getFullPathName(),
                             "--mixed-output", outputMixed.getFullPathName(),
                             "--genre", genre,
                             "--accuracy", juce::String (accuracy, 3),
                             "--expression", juce::String (expression, 3),
                             "--repair", juce::String (repair, 3),
                             "--timing-tightness", juce::String (timingTightness, 3),
                             "--humanize", juce::String (humanize, 3),
                             "--mix-strength", juce::String (mixStrength, 3) };
    if (referenceFile.existsAsFile()) args.addArray ({ "--reference", referenceFile.getFullPathName() });
    return launchEngine (args, log);
}

bool ForgeEngineBridge::runBuildStack (const juce::File& input,
                                       const juce::File& outputDirectory,
                                       juce::String genre,
                                       bool hostedNeural,
                                       float stackSize, float width, float tightness,
                                       float harmonyIntensity, float octaveBlend, float character,
                                       int diffusionSteps, float identityFocus, juce::String& log)
{
    outputDirectory.createDirectory();
    juce::StringArray args { "build-stack", "--input", input.getFullPathName(),
                             "--output-dir", outputDirectory.getFullPathName(),
                             "--genre", genre,
                             "--stack-size", juce::String (stackSize, 3),
                             "--width", juce::String (width, 3),
                             "--tightness", juce::String (tightness, 3),
                             "--harmony-intensity", juce::String (harmonyIntensity, 3),
                             "--octave-blend", juce::String (octaveBlend, 3),
                             "--character", juce::String (character, 3),
                             "--diffusion-steps", juce::String (diffusionSteps),
                             "--identity-focus", juce::String (identityFocus, 3) };
    if (referenceFile.existsAsFile()) args.addArray ({ "--reference", referenceFile.getFullPathName() });
    if (hostedNeural) args.add ("--hosted-neural");
    return launchEngine (args, log);
}
