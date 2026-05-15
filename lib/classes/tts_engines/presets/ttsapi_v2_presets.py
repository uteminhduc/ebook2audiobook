from lib.conf_models import TTS_ENGINES, default_engine_settings

models = {
    "internal": {
        "lang": "vie",
        "repo": "ttsapi-v2",
        "sub": "",
        "voice": default_engine_settings[TTS_ENGINES['TTSAPIV2']]['voice'],
        "files": default_engine_settings[TTS_ENGINES['TTSAPIV2']]['files'],
        "samplerate": default_engine_settings[TTS_ENGINES['TTSAPIV2']]['samplerate']
    }
}
