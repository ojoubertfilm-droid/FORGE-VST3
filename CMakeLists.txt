cmake_minimum_required(VERSION 3.24)
project(FORGE VERSION 0.8.0 LANGUAGES C CXX)

if (NOT WIN32)
    message(FATAL_ERROR "FORGE is the Windows x64 VST3 build. Configure this project on Windows x64.")
endif()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

if (MSVC)
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
endif()

include(FetchContent)
FetchContent_Declare(
    JUCE
    GIT_REPOSITORY https://github.com/juce-framework/JUCE.git
    GIT_TAG 8.0.15
    GIT_SHALLOW TRUE
)
FetchContent_MakeAvailable(JUCE)

juce_add_plugin(FORGE
    COMPANY_NAME "OJ Labs"
    BUNDLE_ID "com.ojlabs.forge"
    COMPANY_WEBSITE "https://github.com/ojoubertfilm-droid/FORGE-VST3"
    COMPANY_EMAIL ""
    PLUGIN_MANUFACTURER_CODE Ojrb
    PLUGIN_CODE Frge
    FORMATS VST3 Standalone
    PRODUCT_NAME "FORGE"
    DESCRIPTION "FORGE Vocal Producer for Metalcore, Post-Hardcore, Alt Metal and Pop-Punk"
    IS_SYNTH FALSE
    NEEDS_MIDI_INPUT FALSE
    NEEDS_MIDI_OUTPUT FALSE
    IS_MIDI_EFFECT FALSE
    EDITOR_WANTS_KEYBOARD_FOCUS TRUE
    COPY_PLUGIN_AFTER_BUILD FALSE
    VST3_CATEGORIES Fx Pitch Shift Dynamics
)

juce_generate_juce_header(FORGE)

target_sources(FORGE PRIVATE
    Source/PluginProcessor.cpp
    Source/PluginProcessor.h
    Source/PluginEditor.cpp
    Source/PluginEditor.h
    Source/ForgeEngineBridge.cpp
    Source/ForgeEngineBridge.h
)

target_compile_definitions(FORGE PUBLIC
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0
    JUCE_USE_WIN_WEBVIEW2=0
    JUCE_VST3_CAN_REPLACE_VST2=0
    WIN32_LEAN_AND_MEAN=1
    NOMINMAX=1
)

target_link_libraries(FORGE PRIVATE
    juce::juce_audio_utils
    juce::juce_dsp
    juce::juce_gui_extra
    PUBLIC
    juce::juce_recommended_config_flags
    juce::juce_recommended_warning_flags
    juce::juce_recommended_lto_flags
)
