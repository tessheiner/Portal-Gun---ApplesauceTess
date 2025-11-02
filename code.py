# Code written primarily by ChatGPT
# Portal GUn by applesauceTess

import time
import board
import busio
from adafruit_ht16k33.segments import Seg14x4
from adafruit_seesaw import seesaw, rotaryio, digitalio
import adafruit_aw9523

class PortalGun:
    def __init__(self):
        # ---- I2C setup ----
        self.i2c = busio.I2C(board.SCL, board.SDA)

        # ---- Rotary Encoder ----
        self.encoder_ss = seesaw.Seesaw(self.i2c, addr=0x36)
        self.encoder = rotaryio.IncrementalEncoder(self.encoder_ss)
        self.button = digitalio.DigitalIO(self.encoder_ss, 24)

        # ---- Display ----
        self.display = Seg14x4(self.i2c, address=0x70)
        self.display.brightness = 0.5

        # ---- GPIO Expander ----
        self.aw = adafruit_aw9523.AW9523(self.i2c)
        self.front_leds = [self.aw.get_pin(i) for i in (1,6,15)]
        self.top_leds = [self.aw.get_pin(0)]
        for led in self.front_leds + self.top_leds:
            led.switch_to_output(value=True)  # active-low → True = off

        # ---- Universe state ----
        self.letters = [chr(i) for i in range(ord('A'), ord('Z')+1)]
        self.letter_index = 2
        self.number = 137
        self.portal_on = False

        # ---- Encoder state ----
        self.last_position = self.encoder.position

        # ---- Button state ----
        self.button_pressed = False
        self.press_time = None
        self.long_press_threshold = 1.0
        self.long_press_active = False  # Track if long press triggered

        # ---- Top LED blink state ----
        self.blink_interval = 2
        self.last_blink = time.monotonic()
        self.blink_state = False

        # ---- Front LED wave state ----
        self.front_step_index = 0
        self.front_step_delay = 0.1
        self.front_wave_last = time.monotonic()
        self.front_hold = False
        self.front_hold_start = None
        self.front_hold_time = 5.0

    # ---- LED helpers ----
    def leds_on(self, leds):
        for l in leds:
            l.value = False  # active-low

    def leds_off(self, leds):
        for l in leds:
            l.value = True

    def animation_flash(self, times=3, interval=0.1):
        for _ in range(times):
            self.leds_on(self.front_leds)
            time.sleep(interval)
            self.leds_off(self.front_leds)
            time.sleep(interval)

    # ---- Display helpers ----
    def show_universe(self):
        text = f"{self.letters[self.letter_index]}{self.number:03d}"
        self.display.fill(0)
        self.display.print(text)
        self.display.show()

    def show_off(self):
        self.display.fill(0)
        self.display.show()

    def show_rick(self):
        self.display.fill(0)
        self.display.print("RICK")
        self.display.show()

    # ---- Button & Encoder ----
    def handle_button(self):
        now = time.monotonic()
        if not self.button.value:  # pressed
            if not self.button_pressed:
                self.button_pressed = True
                self.press_time = now
            elif now - self.press_time > self.long_press_threshold and not self.long_press_active:
                # Long press triggered
                self.long_press_active = True
                self.show_rick()
                self.animation_flash()
                self.portal_on = False
                self.leds_off(self.front_leds + self.top_leds)
                self.show_off()
        else:  # released
            if self.button_pressed and not self.long_press_active:
                # Short press
                self.portal_on = not self.portal_on
                self.animation_flash()
                if self.portal_on:
                    self.show_universe()
                else:
                    self.show_off()
                    self.leds_off(self.front_leds + self.top_leds)
            self.button_pressed = False
            self.long_press_active = False

    def handle_encoder(self):
        pos = self.encoder.position
        if pos != self.last_position:
            diff = pos - self.last_position
            self.last_position = pos
            self.number += diff
            if self.number > 999:
                self.number = 0
                self.letter_index = (self.letter_index + 1) % len(self.letters)
            elif self.number < 0:
                self.number = 999
                self.letter_index = (self.letter_index - 1) % len(self.letters)
            if self.portal_on:
                self.show_universe()

    # ---- Animations ----
    def update_top_leds(self):
        now = time.monotonic()

        if not self.portal_on:
            self.leds_off(self.top_leds)
            self.blink_state = False
            return

        # --- Custom 2s ON, quick OFF flash pattern ---
        cycle_time = 2.1  # total time of one full cycle (2s on + 0.1s off)
        flash_off_duration = 0.1  # how long the LED blinks off

        elapsed = (now - self.last_blink) % cycle_time

        if elapsed < 2.0:
            # LED ON phase
            for l in self.top_leds:
                l.value = False  # active-low = on
        else:
            # Quick blink OFF phase
            for l in self.top_leds:
                l.value = True   # off

        # reset the reference timer occasionally to avoid overflow
        if now - self.last_blink > 60:
            self.last_blink = now


    def update_front_leds(self):
        now = time.monotonic()
        if not self.portal_on:
            self.leds_off(self.front_leds)
            self.front_step_index = 0
            self.front_hold = False
            return

        if self.front_hold:
            if now - self.front_hold_start >= self.front_hold_time:
                self.leds_off(self.front_leds)
                self.front_hold = False
                self.front_step_index = 0
                self.front_wave_last = now
        else:
            if now - self.front_wave_last >= self.front_step_delay:
                # Turn off previous LED
                self.leds_off(self.front_leds)
                # Light next LED
                led = self.front_leds[self.front_step_index]
                self.leds_on([led])
                self.front_step_index += 1
                if self.front_step_index >= len(self.front_leds):
                    # Enter hold phase → turn **all front LEDs on**
                    self.front_hold = True
                    self.front_hold_start = now
                    self.leds_on(self.front_leds)  # <-- this line ensures all 3 stay on
                self.front_wave_last = now

    # ---- Main update ----
    def update(self):
        self.handle_button()
        self.handle_encoder()
        self.update_top_leds()
        self.update_front_leds()


# ---- Run ----
portal = PortalGun()

while True:
    portal.update()
    time.sleep(0.01)
