import json
import tempfile
from urllib import error as urllib_error
from urllib import request as urllib_request

from pydub import AudioSegment

from lib.classes.tts_engines.common.headers import *
from lib.classes.tts_engines.common.preset_loader import load_engine_presets


class TTSApi(TTSUtils, TTSRegistry, name='ttsapi'):

    def __init__(self, session:DictProxy):
        try:
            self.session = session
            self.models = load_engine_presets(self.session['tts_engine'])
            self.params = {}
            fine_tuned = self.session.get('fine_tuned')
            if fine_tuned not in self.models:
                error = f'Invalid fine_tuned model {fine_tuned}. Available models: {list(self.models.keys())}'
                raise ValueError(error)
            model_cfg = self.models[fine_tuned]
            if 'samplerate' not in model_cfg:
                error = f'fine_tuned model {fine_tuned} is missing required key samplerate.'
                raise ValueError(error)
            settings = default_engine_settings[self.session['tts_engine']]
            self.params['samplerate'] = model_cfg['samplerate']
            self.params['api_url'] = str(settings.get('api_url') or '').strip()
            self.params['api_key'] = str(settings.get('api_key') or '').strip()
            self.params['payload_schema'] = str(settings.get('payload_schema') or 'ttsapi').strip()
            self.params['default_model'] = str(settings.get('model') or '').strip()
            self.params['default_voice'] = str(settings.get('voice') or self.params['default_model'] or '').strip()
            self.params['speed'] = float(settings.get('speed', 1))
            self.params['format'] = str(settings.get('format', 'wav') or 'wav').strip().lower()
            self.params['bitrate'] = int(settings.get('bitrate', 64))
            self.params['timeout'] = int(settings.get('timeout', 300))
            self.params['block_voice'] = None
            self.params['current_voice'] = None
            self.params['inline_voice'] = None
        except Exception as e:
            error = f'__init__() error: {e}'
            raise ValueError(error)

    def _set_voice(self, voice:str|None)->tuple:
        fallback = self.params['default_voice'] if self.params['payload_schema'] == 'openai_speech' else self.params['default_model']
        current_model = voice if voice not in (None, '') else fallback
        if current_model in (None, ''):
            error = 'TTSAPI configuration error: missing model selection.'
            return None, error
        current_model = str(current_model).strip()
        if os.path.exists(current_model):
            error = 'TTSAPI voice/model error: expected a model id, but received a local file path.'
            return None, error
        return current_model, None

    def _convert_sml(self, sml:str, combined_audio:AudioSegment)->tuple:
        m = SML_TAG_PATTERN.fullmatch(sml)
        if not m:
            error = '_convert_sml SML_TAG_PATTERN error: m is empty'
            return False, error
        tag = m.group('tag')
        close = bool(m.group('close'))
        value = m.group('value')
        if tag == 'break':
            silence_time = float(int(random.uniform(0.3, 0.5) * 100) / 100)
            return True, combined_audio + AudioSegment.silent(duration=int(silence_time * 1000), frame_rate=self.params['samplerate'])
        if tag == 'pause':
            silence_time = float(value) if value else float(int(random.uniform(0.6, 1.1) * 100) / 100)
            return True, combined_audio + AudioSegment.silent(duration=int(silence_time * 1000), frame_rate=self.params['samplerate'])
        if tag == 'voice':
            if close:
                self.params['inline_voice'] = None
                voice_orig, error = self._set_voice(self.params['block_voice'])
                if voice_orig is None and error is not None:
                    return False, error
                self.params['current_voice'] = voice_orig
                return True, combined_audio
            error = 'TTSAPI does not support inline [voice:...] tags. Use GUI/CLI/block model selection instead.'
            return False, error
        return True, combined_audio

    def _request_audio(self, text:str, model:str)->bytes:
        if self.params['payload_schema'] == 'openai_speech':
            payload_data = {
                "model": self.params['default_model'],
                "input": text,
                "voice": model,
                "response_format": self.params['format'],
                "speed": self.params['speed'],
            }
        else:
            payload_data = {
                "text": text,
                "model": model,
                "speed": self.params['speed'],
                "format": self.params['format'],
                "bitrate": self.params['bitrate'],
            }
        payload = json.dumps(payload_data, ensure_ascii=False).encode('utf-8')
        headers = {'Content-Type': 'application/json; charset=utf-8'}
        if self.params['api_key']:
            headers['Authorization'] = f"Bearer {self.params['api_key']}"
        req = urllib_request.Request(
            self.params['api_url'],
            data=payload,
            headers=headers,
            method='POST'
        )
        with urllib_request.urlopen(req, timeout=self.params['timeout']) as response:
            return response.read()

    def _convert_audio(self, input_path:str, sentence_file:str)->None:
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
            raise FileNotFoundError('ffmpeg was not found in PATH.')
        output_target = sentence_file[:-5] if sentence_file.endswith('.part') else sentence_file
        output_format = os.path.splitext(output_target)[1].lstrip('.')
        cmd = [
            ffmpeg,
            '-y',
            '-hide_banner',
            '-loglevel',
            'error',
            '-i',
            input_path,
            '-f',
            output_format,
            sentence_file
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        except subprocess.CalledProcessError as e:
            error = e.stderr.strip() if e.stderr else str(e)
            raise RuntimeError(f'ffmpeg conversion failed: {error}') from e

    def convert(self, sentence_file:str, sentence:str, **kwargs)->tuple:
        tmp_input = None
        tmp_output = None
        try:
            if not self.params['api_url']:
                error = 'TTSAPI configuration error: API endpoint is empty.'
                return False, error
            sentence_parts = self._split_sentence_on_sml(sentence)
            self.params['inline_voice'] = None
            self.params['block_voice'] = kwargs.get('block_voice', self.session.get('voice'))
            self.params['current_voice'], error = self._set_voice(self.params['block_voice'])
            if self.params['current_voice'] is None and error is not None:
                return False, error
            combined_audio = AudioSegment.silent(duration=0, frame_rate=self.params['samplerate'])
            for part in sentence_parts:
                part = part.strip()
                if not part:
                    continue
                if SML_TAG_PATTERN.fullmatch(part):
                    success, result = self._convert_sml(part, combined_audio)
                    if not success:
                        return False, result
                    combined_audio = result
                    continue
                model_name = self.params['inline_voice'] or self.params['current_voice']
                audio_bytes = self._request_audio(part, model_name)
                tmp_dir = os.path.join(self.session['process_dir'], 'tmp')
                os.makedirs(tmp_dir, exist_ok=True)
                tmp_input_handle = tempfile.NamedTemporaryFile(dir=tmp_dir, suffix=f".{self.params['format']}", delete=False)
                tmp_input = tmp_input_handle.name
                with tmp_input_handle:
                    tmp_input_handle.write(audio_bytes)
                combined_audio += AudioSegment.from_file(tmp_input, format=self.params['format'])
                Path(tmp_input).unlink(missing_ok=True)
                tmp_input = None
            if len(combined_audio) == 0:
                combined_audio += AudioSegment.silent(duration=400, frame_rate=self.params['samplerate'])
            tmp_dir = os.path.join(self.session['process_dir'], 'tmp')
            os.makedirs(tmp_dir, exist_ok=True)
            tmp_output_handle = tempfile.NamedTemporaryFile(dir=tmp_dir, suffix='.wav', delete=False)
            tmp_output = tmp_output_handle.name
            tmp_output_handle.close()
            combined_audio.export(tmp_output, format='wav')
            tmp_sentence_file = f'{sentence_file}.part'
            self._convert_audio(tmp_output, tmp_sentence_file)
            os.replace(tmp_sentence_file, sentence_file)
            if not os.path.exists(sentence_file):
                error = f'Cannot create {sentence_file}'
                return False, error
            return True, None
        except urllib_error.HTTPError as e:
            details = e.read().decode('utf-8', errors='replace').strip()
            error = f'TTSAPI error {e.code}: {details or e.reason}'
            return False, error
        except urllib_error.URLError as e:
            error = f'TTSAPI connection error: {e.reason}'
            return False, error
        except Exception as e:
            return False, self.log_exception(f'{self.__class__.__name__}.convert()', e)
        finally:
            if tmp_input:
                Path(tmp_input).unlink(missing_ok=True)
            if tmp_output:
                Path(tmp_output).unlink(missing_ok=True)

    def create_vtt(self, all_sentences:list)->bool:
        if self._build_vtt_file(all_sentences):
            return True
        return False


class TTSApiV2(TTSApi, name='ttsapi-v2'):
    pass
