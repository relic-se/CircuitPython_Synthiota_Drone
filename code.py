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

PAGES = const(2)
PAGE_TITLES = ("OSC", "EFX")
PAGE_LABELS = (
    ("FQ","DT","VR","VA","TR","TA","FR","FA"),
    ("ET","ED","EM","DD","DM","PR","PF","PM")
)

WAVEFORMS = [
    relic_waveform.square(),
    relic_waveform.saw(),
    relic_waveform.triangle(),
    relic_waveform.sine(),
    relic_waveform.noise(),
]

LED_COLOR = const(0xFF00FF)

PARAM_WINDOW = 0.01
PARAM_SMOOTHING = 0.2

class Parameter:
    def __init__(self, value: float = 0):
        self._value = value
        self._last_value = None
        self._active = False
        
    def deactivate(self) -> None:
        self._active = False

    def update(self, value: float) -> float:
        if self._last_value is None or abs(value - self._last_value) >= PARAM_WINDOW:
            self._last_value = value
        if abs(self._value - self._last_value) < PARAM_WINDOW:
            self._active = True
        if self._active:
            self._value += (self._last_value - self._value) * PARAM_SMOOTHING
        return self._value
    
    @property
    def value(self) -> float:
        return self._value
    
    @value.setter
    def value(self, value: float) -> None:
        self._value = value
        self.deactivate()

parameters = [
    [Parameter() for i in range(len(PAGE_LABELS[j]))]
    for j in range(PAGES)
]

# hardware and audio
displayio.release_displays()
synthiota = Synthiota(
    sample_rate=32000,
    channel_count=1,
)
synthiota.pot_leds = LED_COLOR

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

voice = Drone(synth, oscillators=8)
voice.amplitude = 0.05

# ui
TITLE_HEIGHT = 20
LABEL_HEIGHT = 10
BAR_HEIGHT = synthiota.display.height-TITLE_HEIGHT-LABEL_HEIGHT
BAR_WIDTH = synthiota.display.width//8

root_group = displayio.Group()
synthiota.display.root_group = root_group
palette = displayio.Palette(1)
palette[0] = 0xFFFFFF

root_group.append(Label(
    font=FONT, text="Drone", color=0xFFFFFF, scale=2,
    anchored_position=(0, TITLE_HEIGHT//2),
    anchor_point=(0, 0.5),
))

pages_group = displayio.Group()
root_group.append(pages_group)

for i in range(PAGES):
    page_group = displayio.Group()
    page_group.hidden = True
    pages_group.append(page_group)

    page_group.append(Label(
        font=FONT, text=PAGE_TITLES[i], color=0xFFFFFF, scale=2,
        anchored_position=(synthiota.display.width-3, TITLE_HEIGHT//2),
        anchor_point=(1, 0.5),
    ))

    label_group = displayio.Group()
    page_group.append(label_group)

    bar_group = displayio.Group()
    page_group.append(bar_group)
    
    for j, label in enumerate(PAGE_LABELS[i]):
        label_group.append(Label(
            font=FONT, text=label, color=0xFFFFFF,
            anchored_position=(j*BAR_WIDTH+BAR_WIDTH//2, TITLE_HEIGHT+LABEL_HEIGHT//2),
            anchor_point=(0.5, 0.5),
        ))
        bar_group.append(vectorio.Rectangle(
            pixel_shader=palette,
            width=BAR_WIDTH, height=BAR_HEIGHT,
            x=j*BAR_WIDTH, y=TITLE_HEIGHT+LABEL_HEIGHT,
        ))

page = None
def set_page(index: int = 0) -> None:
    global page
    index = min(max(index, 0), PAGES-1)
    if index == page:
        return
    if page is not None:
        for parameter in parameters[page]:
            parameter.deactivate()
    page = index
    for i, page_group in enumerate(pages_group):
        page_group.hidden = i != page
    synthiota.mode_leds = [LED_COLOR if page == i else 0x000000 for i in range(3)]
set_page()

waveform = None
def set_waveform(index: int = 0) -> None:
    global waveform
    index = min(max(index, 0), len(WAVEFORMS))
    if index == waveform:
        return
    waveform = index
    voice.waveform = WAVEFORMS[waveform]
set_waveform()

def map_value(value: float, min_val: float, max_val: float, exp: int = 1) -> float:
    return pow(value, exp) * (max_val - min_val) + min_val

def map_rate(value: float) -> float:
    return map_value(value, 0.1, 8, 3)

while True:
    synthiota.update()
    for i, parameter in enumerate(parameters[page]):
        parameter.update(synthiota.pots[i])

    if page == 0:
        voice.frequency = map_value(parameters[0][0].value, 10, 400, 2)
        voice.detune = parameters[0][1].value

        voice.vibrato_rate = map_rate(parameters[0][2].value)
        voice.vibrato_depth = parameters[0][3].value

        voice.tremolo_rate = map_rate(parameters[0][4].value)
        voice.tremolo_depth = parameters[0][5].value

        voice.filter_rate = map_rate(parameters[0][6].value)
        voice.filter_depth = map_value(parameters[0][7].value, 0, synthiota.sample_rate / 4)

    elif page == 1:
        effect_echo.delay_ms = map_value(parameters[0][0].value, 25, 500, 2)
        effect_echo.decay = parameters[1][1].value
        effect_echo.mix = parameters[1][2].value

        effect_distortion.drive = parameters[1][3].value
        effect_distortion.mix = parameters[1][4].value

        effect_phaser.frequency.rate = map_rate(parameters[1][5].value)
        effect_phaser.feedback = parameters[1][6].value
        effect_phaser.mix = parameters[1][7].value

    if (value := synthiota.left_slider.value) is not None:
        voice.filter_frequency = map_value(value, 20, synthiota.sample_rate / 2, 3)
    if (value := synthiota.right_slider.value) is not None:
        voice.filter_resonance = map_value(value, 0.7, 16, 2)

    if synthiota.encoder_button.pressed:
        if not voice.pressed:
            voice.press()
        else:
            voice.release()

    if synthiota.octave_up_button.pressed:
        set_waveform(waveform + 1)
    if synthiota.octave_down_button.pressed:
        set_waveform(waveform - 1)

    if synthiota.encoder.position != 0:
        set_page(page + (1 if synthiota.encoder.position < 0 else -1))
        synthiota.encoder.position = 0

    for i in range(8):
        bar = pages_group[page][2][i]
        bar.height = int(BAR_HEIGHT * parameters[page][i].value)
        bar.y = synthiota.display.height - bar.height
