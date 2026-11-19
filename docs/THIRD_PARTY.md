# Third-party software and models

claude-voice-kit's own code is in the public domain ([The Unlicense](../LICENSE)). It **does not bundle** any
third-party code or model weights. The installer downloads them onto your Mac from their official sources (PyPI,
Hugging Face, Homebrew), and each keeps its own licence. Using them is subject to those licences.

## Models
| Model | Used for | Licence |
|---|---|---|
| [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) ([MLX build](https://huggingface.co/mlx-community/Kokoro-82M-bf16)) | text-to-speech | Apache-2.0 |
| [Parakeet unified EN 0.6B](https://huggingface.co/nvidia/parakeet-unified-en-0.6b) ([GGUF build](https://huggingface.co/handy-computer/parakeet-unified-en-0.6b-gguf)) | speech-to-text | [NVIDIA Open Model License](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/) |
| spaCy `en_core_web_sm` | grammar for pronunciation | MIT |

## Libraries (installed into the kit's own Python environments)
| Package | Used for | Licence |
|---|---|---|
| [mlx-audio](https://pypi.org/project/mlx-audio/) / MLX | running Kokoro on the Apple GPU | MIT |
| [misaki](https://pypi.org/project/misaki/) | text → phonemes | Apache-2.0 |
| [phonemizer-fork](https://pypi.org/project/phonemizer-fork/) and espeak-ng (via `espeakng-loader`) | pronunciation of unknown words | GPL-3.0 |
| [spaCy](https://pypi.org/project/spacy/) | part-of-speech tagging | MIT |
| [PyTorch](https://pypi.org/project/torch/) | pulled in by misaki's optional transformer mode | Apache-2.0 (per current package metadata) |
| [transcribe-cpp](https://pypi.org/project/transcribe-cpp/) ([transcribe.cpp](https://github.com/handy-computer/transcribe.cpp)) | Parakeet inference | MIT |
| [sounddevice](https://pypi.org/project/sounddevice/), [soundfile](https://pypi.org/project/soundfile/) | microphone / audio files | MIT / BSD-3-Clause |
| [huggingface-hub](https://pypi.org/project/huggingface-hub/), [numpy](https://pypi.org/project/numpy/) | model download / arrays | Apache-2.0 / BSD-3-Clause |

## Applications (installed with Homebrew if missing)
| App | Used for | Licence |
|---|---|---|
| [Hammerspoon](https://www.hammerspoon.org) | hotkeys, push-to-talk, notifications | MIT |
| [uv](https://github.com/astral-sh/uv) | Python environments | Apache-2.0 |

## Optional
| App | Used for | Licence |
|---|---|---|
| [Handy](https://handy.computer) | free dictation; shares the Parakeet model | MIT |
| [herdr](https://herdr.dev) | terminal workspace for agents; fullest voice control | Apache-2.0 |

Licences were checked against each project's published metadata. If you redistribute any of these components yourself,
follow their licences, notably GPL-3.0 for espeak-ng / phonemizer and the NVIDIA Open Model License for Parakeet.
