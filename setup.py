#!/usr/bin/env python3
import os

from setuptools import setup

BASEDIR = os.path.abspath(os.path.dirname(__file__))


def get_version():
    """ Find the version of the package"""
    version = None
    version_file = os.path.join(BASEDIR, 'ovos_tts_plugin_mimic3', 'version.py')
    major, minor, build, alpha = (None, None, None, None)
    with open(version_file) as f:
        for line in f:
            if 'VERSION_MAJOR' in line:
                major = line.split('=')[1].strip()
            elif 'VERSION_MINOR' in line:
                minor = line.split('=')[1].strip()
            elif 'VERSION_BUILD' in line:
                build = line.split('=')[1].strip()
            elif 'VERSION_ALPHA' in line:
                alpha = line.split('=')[1].strip()

            if ((major and minor and build and alpha) or
                    '# END_VERSION_BLOCK' in line):
                break
    version = f"{major}.{minor}.{build}"
    if alpha and int(alpha) > 0:
        version += f"a{alpha}"
    return version


def package_files(directory):
    paths = []
    for (path, directories, filenames) in os.walk(directory):
        for filename in filenames:
            paths.append(os.path.join('..', path, filename))
    return paths


def required(requirements_file):
    """ Read requirements file and remove comments and empty lines. """
    with open(os.path.join(BASEDIR, requirements_file), 'r') as f:
        requirements = f.read().splitlines()
        if 'MYCROFT_LOOSE_REQUIREMENTS' in os.environ:
            print('USING LOOSE REQUIREMENTS!')
            requirements = [r.replace('==', '>=').replace('~=', '>=') for r in requirements]
        return [pkg for pkg in requirements
                if pkg.strip() and not pkg.startswith("#")]


def get_lang_extras():
    # Create language-specific extras
    langs = ["de", "es", "fa", "fr", "it", "nl", "ru", "sw"]
    extras = {lang: f"mycroft-mimic3-tts[{lang}]" for lang in langs}
    extras["all"] = [f"mycroft-mimic3-tts[{lang}]" for lang in langs]
    return extras


PLUGIN_ENTRY_POINT = "ovos-tts-plugin-mimic3 = ovos_tts_plugin_mimic3:Mimic3TTSPlugin"
SAMPLE_CONFIGS = 'ovos-tts-plugin-mimic3.config = ovos_tts_plugin_mimic3:Mimic3TTSPluginConfig'

setup(
    name="ovos-tts-plugin-mimic3",
    version=get_version(),
    description="Text to speech plugin for OpenVoiceOS using Mimic3",
    url="https://github.com/OpenVoiceOS/ovos-tts-plugin-mimic3",
    author="Michael Hansen",
    license="AGPL",
    packages=['ovos_tts_plugin_mimic3'],
    install_requires=required("requirements.txt"),
    extras_require=get_lang_extras(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Text Processing :: Linguistic",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
    keywords="mycroft plugin tts mimic mimic3",
    entry_points={"mycroft.plugin.tts": PLUGIN_ENTRY_POINT,
                  'mycroft.plugin.tts.config': SAMPLE_CONFIGS},
)
