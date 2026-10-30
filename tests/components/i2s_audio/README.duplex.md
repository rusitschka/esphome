# ESP32-S3-BOX-3 duplex and clock keep-alive

This backport targets ESPHome **2026.10.1** (tag `4ea26ed65f`) and ESP-IDF **5.5.6**.
It adapts native full-duplex support from [PR 19959](https://github.com/esphome/esphome/pull/19959)
and its stream-info fix from [PR 20984](https://github.com/esphome/esphome/pull/20984).
The 2026.10.1 speaker task and non-duplex channel lifecycle are retained.

## Behavior

The bus allocates RX and TX together once, retaining the channels and their GPIO routing.
RX drives the shared clocks. Bus-level `keep_alive: true` keeps RX enabled between
capture and playback sessions, including when both clients are idle. It requires
`full_duplex: true`; both options default to false.

TX and the speaker task still stop between playback sessions, allowing the stock
`speaker.is_playing` waits and wake-word restart to finish normally. Before starting
the microphone task, a bounded DMA backlog is discarded using the driver's buffer size.
A pending task is never reacquired; cancelling a pending microphone start releases its listener.

Validation requires one standard I2S microphone, at least one standard speaker and matching
sample rate, bit width, clock role, APLL/MCLK settings and mono/stereo slot layout.
PDM, SPDIF and non-Philips framing are rejected. Speakers sharing a bus must also share
DOUT, channel selection and framing. Playback must match the fixed output format;
the existing bit-depth narrowing remains available.

## Box overlay

Load `common-box3-keep-alive.yaml` after the stock Box package, and load this checkout's
`esphome/components` as a local `external_components` source for `i2s_audio` only.
The tested base package revision is `a159d9aae35a4d0123aa0bc1d2ceaa5357c6cbad` in
`esphome/wake-word-voice-assistants`. Recheck the overlay automations when updating it.

The ADC and microphone run at 48 kHz with **33 dB** gain. A built-in microphone resampler
provides **16 kHz** to Assist and microWakeWord. DAC, speaker and announcement playback
remain **48 kHz / 16-bit mono**. Capture-state and mute automations name the hardware
microphone explicitly, avoiding ambiguous IDs after adding the resampler. Mapping-form
automations replace the original action lists rather than appending duplicates.

## Validation

- 23 configuration/code-generation tests passed, including default-off behavior and invalid bus settings.
- Ruff, clang-format and language-schema extraction passed; both flags appear with default false.
- Complete Box firmware built through `esphome.sh` with ESPHome 2026.10.1 / ESP-IDF 5.5.6.
- Image: 4,871,611 bytes; static RAM: 155,727 bytes. Runtime heap/CPU use was not measured.
- Four host-side scheduling scenarios passed using the actual microphone start/stop/loop
  method bodies with mocked FreeRTOS operations: immediate cancellation, delayed task startup,
  cancellation after driver failure and two listeners releasing in turn.
- After OTA deployment, logs confirmed 48 kHz ADC, 16 kHz resampler and active wake-word detection.
  The tester reported correct answers and no audible clicks in two German voice interactions.
  Those interactions occurred after the bounded log capture ended; the listening result is tester-reported.
  Whisper and Piper were unchanged. A 2–3 second delay from displayed text to speech was also reported.

This is a short hardware test, not a long-term reliability or audio-quality guarantee.
Boot clicks and amplifier power transitions may remain. Keeping clocks active and
resampling use additional power, CPU and DMA RAM. This adds neither echo cancellation
nor barge-in; the stock policy of stopping wake-word detection during playback is retained.
