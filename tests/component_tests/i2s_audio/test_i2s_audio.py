"""Tests for the i2s_audio full duplex bus."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from esphome import config_validation as cv
from esphome.components.i2s_audio import _validate_full_duplex
from esphome.core import CORE, ID

BUS_ID = "duplex_bus"


def _device(**overrides: Any) -> dict[str, Any]:
    return {
        "platform": "i2s_audio",
        "id": ID("device", is_declaration=True),
        "i2s_audio_id": ID(BUS_ID, is_declaration=False),
        "i2s_dout_pin": 17,
        "channel": "stereo",
        "i2s_comm_fmt": "stand_i2s",
        "sample_rate": 48000,
        "bits_per_sample": 32,
        "i2s_mode": "primary",
        "use_apll": False,
        "mclk_multiple": 256,
    } | overrides


def _full_config(
    microphones: list[dict[str, Any]], speakers: list[dict[str, Any]]
) -> dict[str, Any]:
    return {"microphone": microphones, "speaker": speakers}


def test_full_duplex_generates_code(
    generate_main: Callable[[str | Path], str],
) -> None:
    """The microphone and every speaker are registered with the bus and the full duplex code is enabled."""
    main_cpp = generate_main(
        "tests/component_tests/i2s_audio/test_full_duplex_multiple_speakers.yaml"
    )

    assert "duplex_bus->set_keep_alive(true);" in main_cpp
    assert "duplex_bus->set_audio_in(duplex_mic);" in main_cpp
    assert "duplex_bus->set_audio_out(duplex_speaker_a);" in main_cpp
    assert "duplex_bus->set_audio_out(duplex_speaker_b);" in main_cpp
    assert "USE_I2S_AUDIO_FULL_DUPLEX" in {define.name for define in CORE.defines}


_OTHER_BUS = _device(i2s_audio_id=ID("other_bus", is_declaration=False))


@pytest.mark.parametrize(
    ("microphones", "speakers"),
    [
        pytest.param([_device(pdm=False)], [_device(spdif_mode=False)], id="matching"),
        pytest.param(
            [_device(), _OTHER_BUS], [_device(), _OTHER_BUS], id="other-bus-ignored"
        ),
        pytest.param(
            [_device()], [_device(), _device(), _device()], id="several-speakers"
        ),
    ],
)
def test_full_duplex_accepts(
    microphones: list[dict[str, Any]], speakers: list[dict[str, Any]]
) -> None:
    """Devices with the same clock and TX settings share the bus; other buses do not count."""
    _validate_full_duplex(_full_config(microphones, speakers), BUS_ID)


@pytest.mark.parametrize(
    ("microphones", "speakers"),
    [
        ([], [_device()]),
        ([_device()], []),
        ([_device(), _device()], [_device()]),
    ],
)
def test_full_duplex_requires_one_microphone_and_a_speaker(
    microphones: list[dict[str, Any]], speakers: list[dict[str, Any]]
) -> None:
    """Exactly one microphone and at least one speaker must use the bus."""
    with pytest.raises(cv.Invalid, match="exactly one i2s_audio microphone"):
        _validate_full_duplex(_full_config(microphones, speakers), BUS_ID)


@pytest.mark.parametrize(
    ("microphone", "speaker", "error_match"),
    [
        pytest.param(_device(pdm=True), _device(), "PDM microphone", id="pdm"),
        pytest.param(_device(), _device(spdif_mode=True), "SPDIF speaker", id="spdif"),
    ],
)
def test_full_duplex_rejects_unsupported_devices(
    microphone: dict[str, Any], speaker: dict[str, Any], error_match: str
) -> None:
    """PDM receive and SPDIF output cannot share the standard mode clocks."""
    with pytest.raises(cv.Invalid, match=error_match):
        _validate_full_duplex(_full_config([microphone], [speaker]), BUS_ID)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("sample_rate", 16000),
        ("bits_per_sample", 16),
        ("i2s_mode", "secondary"),
        ("use_apll", True),
        ("mclk_multiple", 384),
    ],
)
def test_full_duplex_rejects_mismatched_clock_settings(key: str, value: Any) -> None:
    """Settings that shape the shared clocks must match."""
    with pytest.raises(cv.Invalid, match=f"must use the same '{key}'"):
        _validate_full_duplex(
            _full_config([_device()], [_device(**{key: value})]), BUS_ID
        )


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("i2s_dout_pin", 18),
        ("channel", "mono"),
        ("i2s_comm_fmt", "stand_pcm_long"),
    ],
)
def test_full_duplex_rejects_mismatched_speakers(key: str, value: Any) -> None:
    """Settings that shape the TX channel must match across speakers."""
    with pytest.raises(
        cv.Invalid,
        match=f"speakers on 'full_duplex' bus '{BUS_ID}' must use the same '{key}'",
    ):
        _validate_full_duplex(
            _full_config([_device()], [_device(), _device(**{key: value})]), BUS_ID
        )


@pytest.mark.parametrize("setting", ["stand_msb", "stand_pcm_short"])
def test_full_duplex_rejects_non_philips_framing(setting: str) -> None:
    """The microphone always uses Philips I2S framing."""
    with pytest.raises(cv.Invalid, match="Philips I2S framing"):
        _validate_full_duplex(
            _full_config([_device()], [_device(i2s_comm_fmt=setting)]), BUS_ID
        )


def test_full_duplex_rejects_different_slot_layout() -> None:
    """Stereo RX and mono TX must not generate different word clocks."""
    with pytest.raises(cv.Invalid, match="same mono/stereo slot layout"):
        _validate_full_duplex(
            _full_config([_device(channel="right")], [_device()]), BUS_ID
        )


@pytest.mark.parametrize("full_duplex", [False, True])
def test_optional_modes_codegen(
    generate_main: Callable[[str | Path], str], tmp_path: Path, full_duplex: bool
) -> None:
    """Keep-alive is opt-in; ordinary buses retain their original ownership."""
    source = Path(
        "tests/component_tests/i2s_audio/test_full_duplex_multiple_speakers.yaml"
    )
    config = tmp_path / "optional.yaml"
    config.write_text(
        source.read_text(encoding="utf-8")
        .replace("full_duplex: true", f"full_duplex: {str(full_duplex).lower()}")
        .replace("keep_alive: true\n", ""),
        encoding="utf-8",
    )
    main_cpp = generate_main(config)
    assert (
        "USE_I2S_AUDIO_FULL_DUPLEX" in {define.name for define in CORE.defines}
    ) == full_duplex
    if full_duplex:
        assert "duplex_bus->set_keep_alive(false);" in main_cpp
    else:
        assert "duplex_bus->set_audio_in(" not in main_cpp
        assert "duplex_bus->set_keep_alive(" not in main_cpp


def test_keep_alive_without_duplex_is_invalid(tmp_path: Path) -> None:
    """A persistent RX clock requires the paired-channel ownership model."""
    from esphome.config import load_config

    source = Path(
        "tests/component_tests/i2s_audio/test_full_duplex_multiple_speakers.yaml"
    )
    config = tmp_path / "invalid.yaml"
    config.write_text(
        source.read_text(encoding="utf-8").replace(
            "full_duplex: true", "full_duplex: false"
        ),
        encoding="utf-8",
    )
    CORE.config_path = config
    result = load_config({})
    assert any(
        "'keep_alive' requires 'full_duplex: true'" in str(error)
        for error in result.errors
    )
