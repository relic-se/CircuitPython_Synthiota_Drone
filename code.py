# SPDX-FileCopyrightText: 2026 Cooper Dalrymple (@relic-se)
#
# SPDX-License-Identifier: GPLv3

# TODO: control `synthiota.pot_leds`` to represent `voice.notes` state
# TODO: Use step pads for frequency?

from audiodelays import Echo
from audiofilters import Distortion, DistortionMode, Phaser
from adafruit_display_text.label import Label
import displayio
from relic_synthiota import Synthiota
from relic_synthvoice.drone import Drone
import relic_waveform
from terminalio import FONT
from synthio import Synthesizer, LFO
import vectorio
from micropython import const
from rainbowio import colorwheel
import microcontroller

# improve performance with a light overclock
microcontroller.cpu.frequency = 300_000_000

WAVEFORMS = [
    relic_waveform.square(),
    relic_waveform.square(duty_cycle=0.25),
    relic_waveform.saw(),
    relic_waveform.mix(
        (relic_waveform.saw(), 0.6),
        (relic_waveform.saw(frequency=2), 0.6),
    ),
    relic_waveform.mix(
        (relic_waveform.triangle(), 0.7),
        (relic_waveform.saw(frequency=2.0), 0.1),
        (relic_waveform.saw(frequency=3.0), 0.1),
        (relic_waveform.saw(frequency=4.0), 0.1),
    ),
    relic_waveform.triangle(),
    relic_waveform.sine(),
    relic_waveform.noise(),
]

LED_COLOR = const(0xFF00FF)
LED_PRESS_COLOR = const(0xFFFF00)
LED_LATCH_COLOR = const(0xFF0000)

# hardware and audio
displayio.release_displays()
synthiota = Synthiota(
    sample_rate=32000,
    channel_count=1,
)

effect_echo = Echo(
    freq_shift=True,
    buffer_size=synthiota.buffer_size,
    sample_rate=synthiota.sample_rate,
    channel_count=synthiota.channel_count,
)
synthiota.mixer.play(effect_echo)

effect_phaser = Phaser(
    frequency=LFO(offset=1000, scale=600),
    buffer_size=synthiota.buffer_size,
    sample_rate=synthiota.sample_rate,
    channel_count=synthiota.channel_count,
)
effect_echo.play(effect_phaser)

effect_distortion = Distortion(
    mode=DistortionMode.OVERDRIVE,
    soft_clip=True,
    buffer_size=synthiota.buffer_size,
    sample_rate=synthiota.sample_rate,
    channel_count=synthiota.channel_count,
)
effect_phaser.play(effect_distortion)

synth = Synthesizer(
    sample_rate=synthiota.sample_rate,
    channel_count=synthiota.channel_count,
)
effect_distortion.play(synth)

voice = Drone(synth, max_oscillators=8)

# parameters
PARAM_WINDOW = 0.01

def map_value(in_value: float, in_minimum: float, in_maximum: float, out_minimum: float, out_maximum: float, clamp: bool = True) -> float:
    if clamp:
        in_value = min(max(in_value, in_minimum), in_maximum)
    return (in_value - in_minimum) / (in_maximum - in_minimum) * (out_maximum - out_minimum) + out_minimum

class Parameter:

    def __init__(self, obj: object = None, name: str = "", minimum: float = 0, maximum: float = 1, value: float = None, shape: int = 1, smoothing: float = 0.5, round: bool = False, window: bool = True):
        self._object = obj
        self._name = name
        self._minimum = minimum
        self._maximum = maximum
        self._shape = max(shape, 1)
        self._smoothing = min(max(smoothing, 0.001), 1)
        self._round = round
        self._window = window

        self.value = minimum if value is None else value
        self._last_value = None

        self._setattr()  # set initial value

    def _get_map_value(self, value: float = None) -> float:
        if value is None:
            value = self._value
        value = min(max(value, 0), 1)
        if self._shape > 1:
            value = pow(value, self._shape)
        value = map_value(value, 0, 1, self._minimum, self._maximum)
        if self._round:
            value = round(value)
        return value
    
    def _setattr(self) -> None:
        if self._object is not None and len(self._name):
            setattr(self._object, self._name, self._map_value)
        
    def deactivate(self) -> None:
        self._active = False

    def update(self, value: float) -> None:
        if value is None:
            return
        if self._last_value is None or abs(value - self._last_value) >= PARAM_WINDOW:
            self._last_value = value
        if not self._window or abs(self._value - self._last_value) < PARAM_WINDOW:
            self._active = True
        if self._active:
            self._value += (self._last_value - self._value) * self._smoothing

            # update mapped value
            self._map_value = self._get_map_value()

            # update object
            self._setattr()
    
    @property
    def value(self) -> float:
        return self._map_value
    
    @value.setter
    def value(self, value: float) -> None:
        self._map_value = min(max(value, self._minimum), self._maximum)

        # calculate relative value
        self._value = map_value(self._map_value, self._minimum, self._maximum, 0, 1)
        if self._shape > 1:
            self._value = pow(self._value, 1 / self._shape)  # invert smoothing

        self._setattr()
        self.deactivate()

    @property
    def raw_value(self) -> float:
        return self._value
    
    @raw_value.setter
    def raw_value(self, value: float) -> None:
        self._value = value
        self._map_value = self._get_map_value()

        self._setattr()
        self.deactivate()


PAGES = (
    (
        "OSC",
        (
            ("LVL", Parameter(synthiota.mixer.voice[0], "level", 0, 1, 0.25)),
            ("OSC", Parameter(voice, "oscillators", 1, 8, 3, round=True)),
            ("FQ", Parameter(voice, "tune", -4, 2, -2)),
            ("DT", Parameter(voice, "detune")),
            ("AMP", Parameter(voice, "amplitude", 0, 1/8, 1/8)),
            ("ATK", Parameter(voice, "attack_time", 0.001, 5, 0.5, 4)),
            ("RLS", Parameter(voice, "release_time", 0.001, 5, 0.5, 4)),
            ("GLD", Parameter(voice, "glide", 0.001, 5, 0.05, 4)),
        )
    ),
    (
        "MOD",
        (
            ("VR", Parameter(voice, "vibrato_rate", 0.1, 8, 1, 3)),
            ("VA", Parameter(voice, "vibrato_depth")),

            ("TR", Parameter(voice, "tremolo_rate", 0.1, 8, 1, 3)),
            ("TA", Parameter(voice, "tremolo_depth")),

            ("FR", Parameter(voice, "filter_rate", 0.1, 8, 1, 3)),
            ("FA", Parameter(voice, "filter_depth")),
        )
    ),
    (
        "EFX",
        (
            ("ET", Parameter(effect_echo, "delay_ms", 25, 500, 250, 2)),
            ("ED", Parameter(effect_echo, "decay", value=0.25)),
            ("EM", Parameter(effect_echo, "mix")),

            ("DD", Parameter(effect_distortion, "drive", value=0.5)),
            ("DM", Parameter(effect_distortion, "mix")),

            ("PR", Parameter(effect_phaser.frequency, "rate", 0.1, 8, 1, 3)),
            ("PF", Parameter(effect_phaser, "feedback", value=0.5)),
            ("PM", Parameter(effect_phaser, "mix")),
        )
    )
)

left_slider_parameter = Parameter(
    voice, "filter_frequency",
    20, synthiota.sample_rate / 2, 2000,
    shape=4, smoothing=0.05, window=False,
)

right_slider_parameter = Parameter(
    voice, "filter_resonance",
    0.7, 16, 1.5,
    shape=2, smoothing=0.05, window=False,
)

# ui
TITLE_HEIGHT = 20
LABEL_HEIGHT = 10
BAR_HEIGHT = synthiota.display.height-TITLE_HEIGHT-LABEL_HEIGHT
BAR_WIDTH = synthiota.display.width//8

root_group = displayio.Group()
synthiota.display.root_group = root_group
palette = displayio.Palette(2)
palette[0] = 0x000000
palette[1] = 0xFFFFFF

root_group.append(Label(
    font=FONT, text="Drone", color=0xFFFFFF, scale=2,
    anchored_position=(0, TITLE_HEIGHT//2),
    anchor_point=(0, 0.5),
))

waveform_bmp = displayio.Bitmap(TITLE_HEIGHT, TITLE_HEIGHT, 2)
waveform_tg = displayio.TileGrid(
    waveform_bmp, pixel_shader=palette,
    x=synthiota.display.width//2,
)
root_group.append(waveform_tg)

pages_group = displayio.Group()
root_group.append(pages_group)

for i, (title, parameters) in enumerate(PAGES):
    page_group = displayio.Group()
    page_group.hidden = True
    pages_group.append(page_group)

    page_group.append(Label(
        font=FONT, text=title, color=0xFFFFFF, scale=2,
        anchored_position=(synthiota.display.width-3, TITLE_HEIGHT//2),
        anchor_point=(1, 0.5),
    ))

    label_group = displayio.Group()
    page_group.append(label_group)

    bar_group = displayio.Group()
    page_group.append(bar_group)
    
    for j, (label, parameter) in enumerate(parameters):
        label_group.append(Label(
            font=FONT, text=label, color=0xFFFFFF,
            anchored_position=(j*BAR_WIDTH+BAR_WIDTH//2, TITLE_HEIGHT+LABEL_HEIGHT//2),
            anchor_point=(0.5, 0.5),
        ))
        bar_group.append(vectorio.Rectangle(
            pixel_shader=palette, color_index=1,
            width=BAR_WIDTH, height=BAR_HEIGHT,
            x=j*BAR_WIDTH, y=TITLE_HEIGHT+LABEL_HEIGHT,
        ))

page = None
def set_page(index: int = 0) -> None:
    global page
    index = min(max(index, 0), len(PAGES)-1)
    if index == page:
        return
    if page is not None:
        for label, parameter in PAGES[page][1]:
            parameter.deactivate()
    page = index
    for i, page_group in enumerate(pages_group):
        page_group.hidden = i != page
    synthiota.mode_leds = [LED_COLOR if page & (1 << i) else 0x000000 for i in range(3)]
set_page()

waveform_index = None
def set_waveform(index: int = 0) -> None:
    global waveform_index
    index = min(max(index, 0), len(WAVEFORMS) - 1)
    if index == waveform_index:
        return
    waveform_index = index
    waveform = WAVEFORMS[waveform_index]

    voice.waveform = waveform

    waveform_bmp.fill(0)
    waveform_min, waveform_max = min(waveform), max(waveform)
    mid_y = waveform_bmp.height // 2
    last_y = mid_y
    for x in range(waveform_bmp.width):
        i = round(x / waveform_bmp.width * len(waveform))
        y = round(map_value(waveform[i], waveform_min, waveform_max, waveform_bmp.height - 1, 0))
        waveform_bmp[x,y] = 1
        if abs(y - last_y) > 1:
            step = 1 if y > last_y else -1
            for j in range(last_y + step, y, step):
                waveform_bmp[x,j] = 1
        last_y = y
    step = 1 if mid_y > last_y else -1
    for y in range(last_y + step, mid_y, step):
        waveform_bmp[x,y] = 1

set_waveform()

def apply_brightness(color: int, value: float) -> int:
    value = min(max(value, 0), 1)
    output = 0x000000
    for i in range(3):
        component = (color >> (8 * i)) & 0xFF
        component = round(component * value) & 0xFF
        output |= component << (8 * i)
    return output

def get_lfo_value(lfo: LFO, max_scale: float = 1, minimum: float = 0, maximum: float = 1) -> float:
    return map_value(lfo.value, lfo.offset - max_scale, lfo.offset + max_scale, minimum, maximum)

latched = False
step_index = None
led_index = None
while True:
    synthiota.update()

    # change page
    if synthiota.encoder.position != 0:
        set_page(page + (1 if synthiota.encoder.position < 0 else -1))
        synthiota.encoder.position = 0

    # update page parameters
    for i, (label, parameter) in enumerate(PAGES[page][1]):
        parameter.update(synthiota.pots[i])

    # update sliders
    left_slider_parameter.update(synthiota.left_slider.value)
    right_slider_parameter.update(synthiota.right_slider.value)

    # control waveform
    if synthiota.up_button.pressed:
        set_waveform(waveform_index + 1)
    if synthiota.down_button.pressed:
        set_waveform(waveform_index - 1)

    # handle latching
    if synthiota.encoder_button.pressed:
        latched = not latched
        if latched and not voice.pressed:
            voice.press()
            led_index = 0
        elif not latched and voice.pressed:
            voice.release()
            led_index = None

    # handle step touches
    try:
        index = "".join(map(lambda x: str(int(x)), synthiota.touched_steps)).rindex("1")
    except ValueError:
        if not latched and voice.pressed:
            voice.release()
            led_index = None
        step_index = None
    else:
        if index != step_index:
            voice.press(48 + index)
            step_index = index
            led_index = index

    # control step leds
    step_leds = [LED_PRESS_COLOR if led_index is not None and led_index == i else (LED_LATCH_COLOR if latched else 0x000000) for i in range(16)]

    # control oscillator leds
    pot_leds = [0x000000 for i in range(8)]
    for i in range(voice.oscillators):
        vibrato_lfo = voice._bend[i].b.a
        tremolo_lfo = voice._amplitude[i].b.a
        color = colorwheel(get_lfo_value(vibrato_lfo, maximum=255))
        color = apply_brightness(color, get_lfo_value(tremolo_lfo))
        pot_leds[i] = color

    # update neopixels
    synthiota.leds[:] = tuple(step_leds) + tuple(pot_leds) + synthiota.mode_leds
    
    # update parameter ui bars
    for i in range(min(8, len(pages_group[page][2]))):
        bar = pages_group[page][2][i]
        bar.height = int(BAR_HEIGHT * PAGES[page][1][i][1].raw_value)
        bar.y = synthiota.display.height - bar.height
