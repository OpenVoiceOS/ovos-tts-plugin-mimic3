import io
import re
import typing
import wave
from pathlib import Path
from os.path import join
from ovos_plugin_manager.tts import TTS
from ovos_utils.xdg_utils import xdg_data_home
from ovos_utils.file_utils import get_cache_directory
from threading import Lock
from mimic3_tts import (
    AudioResult,
    Mimic3Settings,
    Mimic3TextToSpeechSystem,
    SSMLSpeaker,
)


class Mimic3TTSPlugin(TTS):
    """Mycroft interface to Mimic3."""
    default_voices = {
        # TODO add default voice per lang
        "en-us": "en_US/cmu-arctic_low",
        "en-uk": "en_UK/apope_low"
    }

    def __init__(self, lang="en-us", config=None):
        super().__init__(lang, config)
        self.lock = Lock()
        self.lang = self.config.get("language") or self.lang
        preload_voices = self.config.get("preload_voices") or []
        preload_langs = self.config.get("preload_langs") or [self.lang]
        default_voice = self.config.get("voice")
        voice_dirs = self.config.get("voices_directories") or [join(xdg_data_home(), "mimic3", "voices")]
        voice_dl = self.config.get("voices_download_dir") or get_cache_directory("mimic3_voices")

        self.tts = Mimic3TextToSpeechSystem(
            Mimic3Settings(
                voice=default_voice,
                language=self.lang,
                voices_directories=voice_dirs,
                voices_url_format=self.config.get("voices_url_format"),
                speaker=self.config.get("speaker"),
                length_scale=self.config.get("length_scale"),
                noise_scale=self.config.get("noise_scale"),
                noise_w=self.config.get("noise_w"),
                voices_download_dir=voice_dl,
                use_deterministic_compute=self.config.get(
                    "use_deterministic_compute", False
                ),
            )
        )

        if default_voice:
            self.default_voices[self.lang] = default_voice

        for voice in preload_voices:
            self.tts.preload_voice(voice)

        for lang in preload_langs:
            voice = self.default_voices.get(lang)
            if voice:
                self.tts.preload_voice(voice)

    def get_tts(self, sentence, wav_file, lang=None, voice=None, speaker=None):
        """Synthesize audio using Mimic3 on device"""

        # support optional args for lang/voice/etc per request
        # a lock is used because we modify internal self.tts state
        with self.lock:
            def_speaker = self.tts.speaker
            def_voice = self.tts.voice
            if voice:
                self.tts.voice = voice
            elif lang and lang in self.default_voices:
                self.tts.voice = self.default_voices[lang]
            if speaker:
                self.tts.speaker = speaker

            # self.tts.settings.length_scale = length_scale
            # self.tts.settings.noise_scale = noise_scale
            # self.tts.settings.noise_w = noise_w

            sentence, ssml = self._apply_text_hacks(sentence)
            wav_bytes = self._mimic3_synth(sentence, ssml=ssml)

            self.tts.voice = def_voice
            self.tts.speaker = def_speaker

        # Write WAV to file
        Path(wav_file).write_bytes(wav_bytes)

        return (wav_file, None)

    def _apply_text_hacks(self, sentence: str) -> typing.Tuple[str, bool]:
        """Mycroft-specific workarounds for text.

        Returns: (text, ssml)
        """

        # HACK: Mycroft gives "eight a.m.next sentence" sometimes
        sentence = sentence.replace(" a.m.", " a.m. ")
        sentence = sentence.replace(" p.m.", " p.m. ")

        # A I -> A.I.
        sentence = re.sub(
            r"\b([A-Z](?: |$)){2,}",
            lambda m: m.group(0).strip().replace(" ", ".") + ". ",
            sentence,
        )

        # Assume SSML if sentence begins with an angle bracket
        ssml = sentence.strip().startswith("<")

        # HACK: Speak single letters from Mycroft (e.g., "A;")
        if (len(sentence) == 2) and sentence.endswith(";"):
            letter = sentence[0]
            ssml = True
            sentence = f'<say-as interpret-as="spell-out">{letter}</say-as>'
        else:
            # HACK: 'A' -> spell out
            sentence, subs_made = re.subn(
                r"'([A-Z])'",
                r'<say-as interpret-as="spell-out">\1</say-as>',
                sentence,
            )
            if subs_made > 0:
                ssml = True

        return (sentence, ssml)

    def _mimic3_synth(self, text: str, ssml: bool = False) -> bytes:
        """Synthesize audio from text and return WAV bytes"""
        with io.BytesIO() as wav_io:
            wav_file: wave.Wave_write = wave.open(wav_io, "wb")
            wav_params_set = False

            with wav_file:
                try:
                    if ssml:
                        # SSML
                        results = SSMLSpeaker(self.tts).speak(text)
                    else:
                        # Plain text
                        self.tts.begin_utterance()
                        self.tts.speak_text(text)
                        results = self.tts.end_utterance()

                    for result in results:
                        # Add audio to existing WAV file
                        if isinstance(result, AudioResult):
                            if not wav_params_set:
                                wav_file.setframerate(result.sample_rate_hz)
                                wav_file.setsampwidth(result.sample_width_bytes)
                                wav_file.setnchannels(result.num_channels)
                                wav_params_set = True

                            wav_file.writeframes(result.audio_bytes)
                except Exception as e:
                    if not wav_params_set:
                        # Set default parameters so exception can propagate
                        wav_file.setframerate(22050)
                        wav_file.setsampwidth(2)
                        wav_file.setnchannels(1)

                    raise e

            wav_bytes = wav_io.getvalue()

        return wav_bytes

