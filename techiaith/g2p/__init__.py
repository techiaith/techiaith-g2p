"""Y G2P Cymraeg Bangor — the permissive Bangor Welsh G2P: text to Piper phoneme ids.

Deliberately free of third-party imports, so a screen-reader add-on or an API worker can depend
on it without pulling an inference stack.

    from techiaith.g2p import BangorG2P
    ids = BangorG2P(english_mode="native").text_to_ids("Bore da")

The ids feed a matching Piper/VITS voice. Match english_mode and data_version to the model's
.onnx.json -- see https://huggingface.co/techiaith/cy_en_GB-bu_tts
"""
from __future__ import annotations

from .bangor_g2p import BangorG2P, OOVError, PhoneError
from .welsh_normalize import WelshNormalizer

__all__ = ["BangorG2P", "OOVError", "PhoneError", "WelshNormalizer"]
