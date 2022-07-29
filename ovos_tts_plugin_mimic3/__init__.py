import io
import re
import typing
import wave
from os.path import join
from pathlib import Path
from threading import Lock

from mimic3_tts import AudioResult, Mimic3Settings, Mimic3TextToSpeechSystem, SSMLSpeaker
from ovos_plugin_manager.tts import TTS
from ovos_utils.xdg_utils import xdg_data_home


class Mimic3TTSPlugin(TTS):
    """Mycroft interface to Mimic3."""
    default_voices = {
        # TODO add default voice for every lang
        "en": "en_US/cmu-arctic_low",
        "en-uk": "en_UK/apope_low",
        "en-gb": "en_UK/apope_low",
        "de": "de_DE/thorsten_low",
        "bn": "bn/multi_low",
        "af": "af_ZA/google-nwu_low",
        "es": "es_ES/m-ailabs_low",
        "fa": "fa/haaniye_low",
        "fi": "fi_FI/harri-tapani-ylilammi_low",
        "fr": "fr_FR/m-ailabs_low",
        "it": "it_IT/mls_low",
        "ko": "ko_KO/kss_low",
        "nl": "nl/bart-de-leeuw_low",
        "pl": "pl_PL/m-ailabs_low",
        "ru": "ru_RU/multi_low",
        "uk": "uk_UK/m-ailabs_low"
    }

    def __init__(self, lang="en-us", config=None):
        super().__init__(lang, config)
        self.lock = Lock()
        self.lang = self.config.get("language") or self.lang
        preload_voices = self.config.get("preload_voices") or []
        preload_langs = self.config.get("preload_langs") or [self.lang]
        default_voice = self.config.get("voice")
        voice_dl = self.config.get("voices_download_dir") or join(xdg_data_home(), "mycroft", "mimic3", "voices")
        voice_dirs = self.config.get("voices_directories") or [voice_dl]

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
            if lang not in self.default_voices:
                lang = lang.split("-")[0]
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
            elif lang:
                if lang not in self.default_voices:
                    lang = lang.split("-")[0]
                if lang in self.default_voices:
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


# TODO manually check gender of each voice and add below
Mimic3TTSPluginConfig = {
    "af-za": [
        {'voice': 'af_ZA/google-nwu_low', 'speaker': '7214', 'gender': ''},
        {'voice': 'af_ZA/google-nwu_low', 'speaker': '8963', 'gender': ''},
        {'voice': 'af_ZA/google-nwu_low', 'speaker': '7130', 'gender': ''},
        {'voice': 'af_ZA/google-nwu_low', 'speaker': '8924', 'gender': ''},
        {'voice': 'af_ZA/google-nwu_low', 'speaker': '8148', 'gender': ''},
        {'voice': 'af_ZA/google-nwu_low', 'speaker': '1919', 'gender': ''},
        {'voice': 'af_ZA/google-nwu_low', 'speaker': '2418', 'gender': ''},
        {'voice': 'af_ZA/google-nwu_low', 'speaker': '6590', 'gender': ''},
        {'voice': 'af_ZA/google-nwu_low', 'speaker': '0184', 'gender': ''}
    ],
    "bn": [
        {'voice': 'bn/multi_low', 'speaker': 'rm', 'gender': ''},
        {'voice': 'bn/multi_low', 'speaker': '03042', 'gender': ''},
        {'voice': 'bn/multi_low', 'speaker': '00737', 'gender': ''},
        {'voice': 'bn/multi_low', 'speaker': '01232', 'gender': ''},
        {'voice': 'bn/multi_low', 'speaker': '02194', 'gender': ''},
        {'voice': 'bn/multi_low', 'speaker': '3108', 'gender': ''},
        {'voice': 'bn/multi_low', 'speaker': '3713', 'gender': ''},
        {'voice': 'bn/multi_low', 'speaker': '1010', 'gender': ''},
        {'voice': 'bn/multi_low', 'speaker': '00779', 'gender': ''},
        {'voice': 'bn/multi_low', 'speaker': '9169', 'gender': ''},
        {'voice': 'bn/multi_low', 'speaker': '4046', 'gender': ''},
        {'voice': 'bn/multi_low', 'speaker': '5958', 'gender': ''},
        {'voice': 'bn/multi_low', 'speaker': '01701', 'gender': ''},
        {'voice': 'bn/multi_low', 'speaker': '4811', 'gender': ''},
        {'voice': 'bn/multi_low', 'speaker': '0834', 'gender': ''},
        {'voice': 'bn/multi_low', 'speaker': '3958', 'gender': ''}
    ],
    "de-de": [
        {'voice': 'de_DE/thorsten_low', 'speaker': 'default', 'gender': ''},

        {'voice': 'de_DE/thorsten-emotion_low', 'speaker': 'amused', 'gender': ''},
        {'voice': 'de_DE/thorsten-emotion_low', 'speaker': 'angry', 'gender': ''},
        {'voice': 'de_DE/thorsten-emotion_low', 'speaker': 'disgusted', 'gender': ''},
        {'voice': 'de_DE/thorsten-emotion_low', 'speaker': 'drunk', 'gender': ''},
        {'voice': 'de_DE/thorsten-emotion_low', 'speaker': 'neutral', 'gender': ''},
        {'voice': 'de_DE/thorsten-emotion_low', 'speaker': 'sleepy', 'gender': ''},
        {'voice': 'de_DE/thorsten-emotion_low', 'speaker': 'surprised', 'gender': ''},
        {'voice': 'de_DE/thorsten-emotion_low', 'speaker': 'whisper', 'gender': ''},

        {'voice': 'de_DE/m-ailabs_low', 'speaker': 'ramona_deininger', 'gender': ''},
        {'voice': 'de_DE/m-ailabs_low', 'speaker': 'karlsson', 'gender': ''},
        {'voice': 'de_DE/m-ailabs_low', 'speaker': 'rebecca_braunert_plunkett', 'gender': ''},
        {'voice': 'de_DE/m-ailabs_low', 'speaker': 'eva_k', 'gender': ''},
        {'voice': 'de_DE/m-ailabs_low', 'speaker': 'angela_merkel', 'gender': ''}
    ],
    "el-gr": [
        {'voice': 'el_GR/rapunzelina_low', 'speaker': 'default', 'gender': ''}
    ],
    "en-uk": [
        {"voice": "en_UK/apope_low", "gender": "male", "speaker": "default"}
    ],
    "en-us": [
        {"voice": "en_US/cmu-arctic_low", "speaker": "slt", "gender": "female"},
        {"voice": "en_US/cmu-arctic_low", "speaker": "awb", "gender": "male"},
        {"voice": "en_US/cmu-arctic_low", "speaker": "rms", "gender": "male"},
        {"voice": "en_US/cmu-arctic_low", "speaker": "ksp", "gender": "male"},
        {"voice": "en_US/cmu-arctic_low", "speaker": "clb", "gender": "female"},
        {"voice": "en_US/cmu-arctic_low", "speaker": "aew", "gender": "male"},
        {"voice": "en_US/cmu-arctic_low", "speaker": "bdl", "gender": "male"},
        {"voice": "en_US/cmu-arctic_low", "speaker": "lnh", "gender": "female"},

        {"voice": "en_US/hifi-tts_low", "speaker": "9017", "gender": "male"},
        {"voice": "en_US/hifi-tts_low", "speaker": "6097", "gender": "male"},
        {"voice": "en_US/hifi-tts_low", "speaker": "92", "gender": "female"},

        {"voice": "en_US/ljspeech_low", "speaker": "default", "gender": "female"},

        {"voice": "en_US/m-ailabs_low", "speaker": "elliot_miller", "gender": "male"},
        {"voice": "en_US/m-ailabs_low", "speaker": "judy_bieber", "gender": "female"},
        {"voice": "en_US/m-ailabs_low", "speaker": "mary_ann", "gender": "female"},

        {'voice': 'en_US/vctk_low', 'speaker': 'p239', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p236', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p264', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p250', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p259', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p247', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p261', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p263', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p283', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p274', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p286', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p276', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p270', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p281', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p277', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p231', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p238', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p271', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p257', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p273', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p284', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p329', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p361', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p287', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p360', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p374', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p376', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p310', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p304', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p340', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p347', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p330', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p308', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p314', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p317', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p339', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p311', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p294', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p305', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p266', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p335', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p334', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p318', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p323', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p351', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p333', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p313', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p316', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p244', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p307', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p363', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p336', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p312', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p267', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p297', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p275', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p295', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p288', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p258', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p301', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p232', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p292', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p272', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p278', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p280', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p341', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p268', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p298', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p299', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p279', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p285', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p326', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p300', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 's5', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p230', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p254', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p269', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p293', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p252', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p345', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p262', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p243', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p227', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p343', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p255', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p229', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p240', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p248', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p253', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p233', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p228', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p251', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p282', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p246', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p234', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p226', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p260', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p245', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p241', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p303', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p265', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p306', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p237', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p249', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p256', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p302', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p364', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p225', 'gender': ''},
        {'voice': 'en_US/vctk_low', 'speaker': 'p362', 'gender': ''}
    ],
    "es-es": [
        {"voice": "es_ES/carlfm_low", "speaker": "default", "gender": ""},

        {'voice': 'es_ES/m-ailabs_low', 'speaker': 'tux', 'gender': ''},
        {'voice': 'es_ES/m-ailabs_low', 'speaker': 'victor_villarraza', 'gender': ''},
        {'voice': 'es_ES/m-ailabs_low', 'speaker': 'karen_savage', 'gender': ''}
    ],
    "fa": [
        {'voice': 'fa/haaniye_low', 'speaker': 'default', 'gender': ''}
    ],
    "fi-fi": [
        {'voice': 'fi_FI/harri-tapani-ylilammi_low', 'speaker': 'default', 'gender': ''}
    ],
    "fr-fr": [
        {'voice': 'fr_FR/m-ailabs_low', 'speaker': 'ezwa', 'gender': ''},
        {'voice': 'fr_FR/m-ailabs_low', 'speaker': 'nadine_eckert_boulet', 'gender': ''},
        {'voice': 'fr_FR/m-ailabs_low', 'speaker': 'bernard', 'gender': ''},
        {'voice': 'fr_FR/m-ailabs_low', 'speaker': 'zeckou', 'gender': ''},
        {'voice': 'fr_FR/m-ailabs_low', 'speaker': 'gilles_g_le_blanc', 'gender': ''},

        {'voice': 'fr_FR/siwis_low', 'speaker': 'default', 'gender': ''},

        {'voice': 'fr_FR/tom_low', 'speaker': 'default', 'gender': ''}
    ],
    "gu-in": [
        {'voice': 'gu_IN/cmu-indic_low', 'speaker': 'cmu_indic_guj_dp', 'gender': ''},
        {'voice': 'gu_IN/cmu-indic_low', 'speaker': 'cmu_indic_guj_ad', 'gender': ''},
        {'voice': 'gu_IN/cmu-indic_low', 'speaker': 'cmu_indic_guj_kt', 'gender': ''}
    ],
    "ha-ne": [
        {'voice': 'ha_NE/openbible_low', 'speaker': 'default', 'gender': ''}
    ],
    "hu-hu": [
        {'voice': 'hu_HU/diana-majlinger_low', 'speaker': 'default', 'gender': ''}
    ],
    "it-it": [
        {'voice': 'it_IT/riccardo-fasol_low', 'speaker': 'default', 'gender': ''},

        {'voice': 'it_IT/mls_low', 'speaker': '1595', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '4974', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '4998', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '6807', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '1989', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '2033', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '2019', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '659', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '4649', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '9772', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '1725', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '10446', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '6348', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '6001', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '9185', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '8842', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '8828', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '12428', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '8181', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '7440', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '8207', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '277', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '5421', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '12804', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '4705', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '7936', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '844', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '6299', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '644', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '8384', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '1157', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '7444', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '643', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '4971', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '4975', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '6744', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '8461', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '7405', 'gender': ''},
        {'voice': 'it_IT/mls_low', 'speaker': '5010', 'gender': ''},

    ],
    "jv-id": [
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '07875', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '05522', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '03424', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '06510', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '03314', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '03187', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '07638', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '06207', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '08736', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '04679', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '01392', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '05540', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '05219', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '00027', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '00264', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '09724', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '04588', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '09039', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '04285', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '05970', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '08305', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '04982', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '08002', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '06080', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '07765', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '02326', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '03727', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '04175', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '06383', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '02884', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '06941', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '08178', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '00658', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '04715', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '05667', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '01519', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '07335', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '02059', 'gender': ''},
        {'voice': 'jv_ID/google-gmu_low', 'speaker': '01932', 'gender': ''},
    ],
    "ko-ko": [
        {'voice': 'ko_KO/kss_low', 'speaker': 'default', 'gender': ''}
    ],
    "ne-np": [{'voice': 'ne_NP/ne-google_low', 'speaker': '0546', 'gender': ''},
              {'voice': 'ne_NP/ne-google_low', 'speaker': '3614', 'gender': ''},
              {'voice': 'ne_NP/ne-google_low', 'speaker': '2099', 'gender': ''},
              {'voice': 'ne_NP/ne-google_low', 'speaker': '3960', 'gender': ''},
              {'voice': 'ne_NP/ne-google_low', 'speaker': '6834', 'gender': ''},
              {'voice': 'ne_NP/ne-google_low', 'speaker': '7957', 'gender': ''},
              {'voice': 'ne_NP/ne-google_low', 'speaker': '6329', 'gender': ''},
              {'voice': 'ne_NP/ne-google_low', 'speaker': '9407', 'gender': ''},
              {'voice': 'ne_NP/ne-google_low', 'speaker': '6587', 'gender': ''},
              {'voice': 'ne_NP/ne-google_low', 'speaker': '0258', 'gender': ''},
              {'voice': 'ne_NP/ne-google_low', 'speaker': '2139', 'gender': ''},
              {'voice': 'ne_NP/ne-google_low', 'speaker': '5687', 'gender': ''},
              {'voice': 'ne_NP/ne-google_low', 'speaker': '0283', 'gender': ''},
              {'voice': 'ne_NP/ne-google_low', 'speaker': '3997', 'gender': ''},
              {'voice': 'ne_NP/ne-google_low', 'speaker': '3154', 'gender': ''},
              {'voice': 'ne_NP/ne-google_low', 'speaker': '0883', 'gender': ''},
              {'voice': 'ne_NP/ne-google_low', 'speaker': '2027', 'gender': ''},
              {'voice': 'ne_NP/ne-google_low', 'speaker': '0649', 'gender': ''}
              ],
    "nl": [
        {'voice': 'nl/bart-de-leeuw_low', 'speaker': 'default', 'gender': ''},

        {'voice': 'nl/flemishguy_low', 'speaker': 'default', 'gender': ''},

        {'voice': 'nl/nathalie_low', 'speaker': 'default', 'gender': ''},

        {'voice': 'nl/pmk_low', 'speaker': 'default', 'gender': ''},

        {'voice': 'nl/rdh_low', 'speaker': 'default', 'gender': ''}
    ],
    "pl-pl": [
        {'voice': 'pl_PL/m-ailabs_low', 'speaker': 'piotr_nater', 'gender': ''},
        {'voice': 'pl_PL/m-ailabs_low', 'speaker': 'nina_brown', 'gender': ''}
    ],
    "ru-ru": [
        {'voice': 'ru_RU/multi_low', 'speaker': 'hajdurova', 'gender': ''},
        {'voice': 'ru_RU/multi_low', 'speaker': 'minaev', 'gender': ''},
        {'voice': 'ru_RU/multi_low', 'speaker': 'nikolaev', 'gender': ''}
    ],
    "sw": [
        {'voice': 'sw/lanfrica_low', 'speaker': 'default', 'gender': ''}
    ],
    "te-in": [
        {'voice': 'te_IN/cmu-indic_low', 'speaker': 'ss', 'gender': ''},
        {'voice': 'te_IN/cmu-indic_low', 'speaker': 'sk', 'gender': ''},
        {'voice': 'te_IN/cmu-indic_low', 'speaker': 'kpn', 'gender': ''}
    ],
    "tn-za": [
        {'voice': 'tn_ZA/google-nwu_low', 'speaker': '1932', 'gender': ''},
        {'voice': 'tn_ZA/google-nwu_low', 'speaker': '0045', 'gender': ''},
        {'voice': 'tn_ZA/google-nwu_low', 'speaker': '3342', 'gender': ''},
        {'voice': 'tn_ZA/google-nwu_low', 'speaker': '4850', 'gender': ''},
        {'voice': 'tn_ZA/google-nwu_low', 'speaker': '6206', 'gender': ''},
        {'voice': 'tn_ZA/google-nwu_low', 'speaker': '3629', 'gender': ''},
        {'voice': 'tn_ZA/google-nwu_low', 'speaker': '9061', 'gender': ''},
        {'voice': 'tn_ZA/google-nwu_low', 'speaker': '6116', 'gender': ''},
        {'voice': 'tn_ZA/google-nwu_low', 'speaker': '7674', 'gender': ''},
        {'voice': 'tn_ZA/google-nwu_low', 'speaker': '0378', 'gender': ''},
        {'voice': 'tn_ZA/google-nwu_low', 'speaker': '5628', 'gender': ''},
        {'voice': 'tn_ZA/google-nwu_low', 'speaker': '8333', 'gender': ''},
        {'voice': 'tn_ZA/google-nwu_low', 'speaker': '8512', 'gender': ''},
        {'voice': 'tn_ZA/google-nwu_low', 'speaker': '0441', 'gender': ''},
        {'voice': 'tn_ZA/google-nwu_low', 'speaker': '6459', 'gender': ''},
        {'voice': 'tn_ZA/google-nwu_low', 'speaker': '4506', 'gender': ''},
        {'voice': 'tn_ZA/google-nwu_low', 'speaker': '7866', 'gender': ''},
        {'voice': 'tn_ZA/google-nwu_low', 'speaker': '8532', 'gender': ''},
        {'voice': 'tn_ZA/google-nwu_low', 'speaker': '2839', 'gender': ''},
        {'voice': 'tn_ZA/google-nwu_low', 'speaker': '7896', 'gender': ''},
        {'voice': 'tn_ZA/google-nwu_low', 'speaker': '1498', 'gender': ''},
        {'voice': 'tn_ZA/google-nwu_low', 'speaker': '1483', 'gender': ''},
        {'voice': 'tn_ZA/google-nwu_low', 'speaker': '8914', 'gender': ''},
        {'voice': 'tn_ZA/google-nwu_low', 'speaker': '6234', 'gender': ''},
        {'voice': 'tn_ZA/google-nwu_low', 'speaker': '9365', 'gender': ''},
        {'voice': 'tn_ZA/google-nwu_low', 'speaker': '7693', 'gender': ''}
    ],
    "uk-uk": [
        {'voice': 'uk_UK/m-ailabs_low', 'speaker': 'obruchov', 'gender': ''},
        {'voice': 'uk_UK/m-ailabs_low', 'speaker': 'shepel', 'gender': ''},
        {'voice': 'uk_UK/m-ailabs_low', 'speaker': 'loboda', 'gender': ''},
        {'voice': 'uk_UK/m-ailabs_low', 'speaker': 'miskun', 'gender': ''},
        {'voice': 'uk_UK/m-ailabs_low', 'speaker': 'sumska', 'gender': ''},
        {'voice': 'uk_UK/m-ailabs_low', 'speaker': 'pysariev', 'gender': ''}
    ],
    "vi-vn": [
        {'voice': 'vi_VN/vais1000_low', 'speaker': 'default', 'gender': ''}
    ],
    "yo": [
        {'voice': 'yo/openbible_low', 'speaker': 'default', 'gender': ''}
    ]
}