from lib.conf_models import TTS_ENGINES, default_engine_settings

models = {
    "internal": {
        "lang": "vie",
        "repo": "ttsapi",
        "sub": "",
        "voice": default_engine_settings[TTS_ENGINES['TTSAPI']]['voice'],
        "files": default_engine_settings[TTS_ENGINES['TTSAPI']]['files'],
        "samplerate": default_engine_settings[TTS_ENGINES['TTSAPI']]['samplerate']
    }
}
