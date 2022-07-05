## Description

OVOS TTS plugin for [Mimic3](https://github.com/MycroftAI/mimic3)

* [Available voices](https://github.com/MycroftAI/mimic3-voices)
* [Documentation](https://mycroft-ai.gitbook.io/docs/mycroft-technologies/mimic-tts/coming-soon-mimic-3)


## Install

Install the necessary system packages:

``` sh
sudo apt-get install libespeak-ng1
```

On 32-bit ARM platforms (a.k.a. `armv7l` or `armhf`), you will also need some extra libraries:

``` sh
sudo apt-get install libatomic1 libgomp1 libatlas-base-dev
```

install the TTS plugin in Mycroft:

`pip install ovos-tts-plugin-mimic3[all}]`

Removing `[all]` will install support for English only.

Additional language support can be selectively installed by replacing `all` with a two-character language code, such as `de` (German) or `fr` (French).
See [`setup.py`](https://github.com/MycroftAI/mimic3/blob/master/setup.py) for an up-to-date list of language codes.

## Configuration

``` json
  "tts": {
    "module": "ovos-tts-plugin-mimic3",
    "ovos-tts-plugin-mimic3": {
      "voice": "en_UK/apope_low",
    }
  }
```


### Advanced config


``` json
"tts": {
  "module": "ovos-tts-plugin-mimic3",
  "ovos-tts-plugin-mimic3": {
      "voice": "en_US/cmu-arctic_low",  // default voice
      "speaker": "fem",  // default speaker
      "length_scale": 1.0,  // speaking rate
      "noise_scale": 0.667,  // speaking variablility
      "noise_w": 1.0  // phoneme duration variablility
  }
}
```
