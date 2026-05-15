import importlib
import threading
from typing import Dict, Any

_lock = threading.Lock()
_presets_cache:Dict[str, Dict[str, Any]] = {}

def load_engine_presets(engine:str)->Dict[str, Any]:
    with _lock:
        if engine in _presets_cache:
            return _presets_cache[engine]
        module_name = engine.replace('-', '_')
        try:
            module = importlib.import_module(f"lib.classes.tts_engines.presets.{module_name}_presets")
        except Exception as e:
            raise ImportError(f"Failed to import presets for engine '{engine}'") from e
        if not hasattr(module, "models"):
            raise RuntimeError(f"'models' not found in {engine}_presets")
        _presets_cache[engine] = module.models
        return module.models
