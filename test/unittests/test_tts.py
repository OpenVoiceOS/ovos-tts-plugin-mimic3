import unittest

from ovos_tts_plugin_mimic3 import Mimic3TTSPlugin


class TestTTS(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        self.mimic = Mimic3TTSPlugin()

    def test_something(self):
        path = "/tmp/hello.wav"
        audio, phonemes = self.mimic.get_tts("hello world", path)
        self.assertEqual(audio, path)
