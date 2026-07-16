# ES8311 BCLK-Derived Clock Design

## Purpose

Allow the existing AIPI-Lite MicroPython application to initialize the
ES8311 capture and playback paths on the supported `ESP32_GENERIC_S3`
MicroPython runtime. That runtime accepts the standard three-wire I2S
constructor (`sck`, `ws`, and `sd`) but does not accept an `mck` argument.

The design keeps the current 16 kHz, 16-bit, mono audio contract. It does not
change firmware images, installer defaults, network behavior, or GPIO10 board
power behavior.

## Selected Approach

Use BCLK as the ES8311 master-clock source.

At the fixed audio configuration, MicroPython I2S runs both slots and provides
a 64-times-sample-rate BCLK: 1.024 MHz at 16 kHz. The ES8311 clock manager will
select BCLK as its input clock and apply a four-times pre-multiplier, preserving
the existing 4.096 MHz internal clock target.

The alternative approaches are intentionally excluded:

- A custom MCLK-capable MicroPython build adds firmware maintenance and is not
  needed for the standard I2S API path.
- A silent retry without `mck` but without changing ES8311 clocking would leave
  the codec configured for an unavailable MCLK input.

## Firmware Changes

### MicroPython I2S construction

`audio_capture.create_i2s()` and `audio_playback.create_i2s()` will construct
I2S using only the supported three-wire interface:

- `sck`: GPIO14 BCLK
- `ws`: GPIO12 LRCLK/WS
- `sd`: GPIO13 for capture or GPIO11 for playback

Both implementations will remove the GPIO6 import and the `mck` constructor
keyword. The fixed I2S format remains 16 kHz, 16-bit, mono.

### ES8311 clock sequence

Replace the MCLK-based sequence with a clearly named BCLK-derived sequence.
For register `0x01`, write `0x9F`: select BCLK, keep BCLK and analog/digital
clock domains enabled, and disable the unused external MCLK input. For register
`0x02`, write `0x10` to apply the four-times pre-multiplier. The existing
register values that define the 16 kHz, 16-bit codec format remain unchanged.

The new sequence is valid only for the fixed 64-times-sample-rate BCLK contract.
Future sample-rate, slot-width, or channel-format changes must explicitly
recalculate and validate the ES8311 pre-multiplier.

## Safety and Error Handling

The change must not add a compatibility fallback or alter GPIO10. Capture keeps
GPIO9 disabled; playback retains its existing mute and speaker-gate cleanup.
The explicit probes remain opt-in. A failed audio probe must remain serial
visible and recoverable through the normal application-first upload flow.

## Tests

Host tests will verify:

- capture and playback pass only `sck`, `ws`, and `sd` pin objects to their I2S
  factories, with no `mck` keyword;
- capture still uses GPIO14/GPIO12/GPIO13 and playback still uses
  GPIO14/GPIO12/GPIO11;
- the ES8311 initialization sequence writes `0x9F` to register `0x01` and
  `0x10` to register `0x02`;
- existing capture bounds, playback mute/gate cleanup, and codec register tests
  continue to pass.

The repository validation set remains:

```bash
python3 -m unittest discover -s tests -v
bash -n install.sh
bash -n tools/setup_micropython_tools.sh
git diff --check
```

## Documentation and Hardware Validation

Update `README.md`, `src/README.md`, `FIRMWARE_IMPL.md`, and
`FIRMWARE_PLAN.md` to describe BCLK-derived ES8311 clocking and remove the
claim that application I2S drives GPIO6 MCLK. `SPEC.md` continues to record
GPIO6 as the board's physical ES8311 MCLK connection; no hardware fact changes.

After application upload, an operator will explicitly run `capture_probe` and
`playback_probe`. Record capture metrics, gain, clipping, noise, dropped
samples, playback volume, output noise, and underruns. The probes must complete
without an I2S constructor keyword error.
