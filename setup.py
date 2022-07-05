from setuptools import setup, find_packages
from os import path, getenv


def get_requirements(requirements_filename: str):
    requirements_file = path.join(path.abspath(path.dirname(__file__)), requirements_filename)
    with open(requirements_file, 'r', encoding='utf-8') as r:
        requirements = r.readlines()
    requirements = [r.strip() for r in requirements if r.strip() and not r.strip().startswith("#")]

    for i in range(0, len(requirements)):
        r = requirements[i]
        if "@" in r:
            parts = [p.lower() if p.strip().startswith("git+http") else p for p in r.split('@')]
            r = "@".join(parts)
            if getenv("GITHUB_TOKEN"):
                if "github.com" in r:
                    r = r.replace("github.com", f"{getenv('GITHUB_TOKEN')}@github.com")
            requirements[i] = r
    return requirements


PLUGIN_ENTRY_POINT = "ovos-tts-plugin-mimic3 = ovos_tts_plugin_mimic3:Mimic3TTSPlugin"
setup(
    name="ovos-tts-plugin-mimic3",
    version="0.0",
    description="Text to speech plugin for OpenVoiceOS using Mimic3",
    url="http://github.com/MycroftAI/plugin-tts-mimic3",
    author="Michael Hansen",
    author_email="michael.hansen@mycroft.ai",
    license="AGPL",
    packages=find_packages(),
    install_requires=get_requirements("requirements.txt"),
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
    entry_points={"mycroft.plugin.tts": PLUGIN_ENTRY_POINT},
)
