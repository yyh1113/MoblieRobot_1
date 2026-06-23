"""
WS2812B LED Controller for the D-Robotics RDK X5 using hardware SPI.

Provides thread-safe control of WS2812B LEDs, state-driven lighting transitions
with caching to avoid redundant SPI bus writes, and dummy fallback support when
running outside the RDK X5 platform.
"""

import logging
import os
import threading
import time
from enum import Enum

log = logging.getLogger("arducam_yolo_web")


class LightState(Enum):
    READY = 1       # Default standby state (soft green)
    SCANNING = 2    # Object detected, active scanning (bright white)
    COMPLETE = 3    # Process complete/image captured (blue pulse feedback)


class ScannerLEDController:
    """Thread-safe state-driven WS2812B controller using hardware SPI."""

    def __init__(self, bus: int = 1, device: int = 0, num_leds: int = 12, speed_hz: int = 6400000):
        self.bus = bus
        self.device = device
        self.num_leds = num_leds
        self.speed_hz = speed_hz
        
        self.lock = threading.Lock()
        self.current_state: LightState | None = None
        self.spi = None
        self.is_mock = False

        # Attempt to open real spidev
        try:
            import spidev
            dev_path = f"/dev/spidev{bus}.{device}"
            if not os.path.exists(dev_path):
                log.warning("=" * 60)
                log.warning("SPI DEVICE NODE NOT FOUND: %s", dev_path)
                log.warning("SPI hardware controller will be mocked (LEDs will not light up).")
                log.warning("💡 Solution: Run 'sudo srpi-config' to enable SPI1, then reboot.")
                log.warning("=" * 60)
                self.is_mock = True
            else:
                self.spi = spidev.SpiDev()
                self.spi.open(bus, device)
                self.spi.max_speed_hz = speed_hz
                self.spi.mode = 0b00
                log.info("=" * 60)
                log.info("Hardware SPI%d.%d initialized for WS2812B at %d Hz.", bus, device, speed_hz)
                log.info("=" * 60)
        except ImportError:
            log.warning("=" * 60)
            log.warning("PYTHON PACKAGE 'spidev' IS MISSING.")
            log.warning("Running in MOCK mode. LEDs will not light up.")
            log.warning("💡 Solution: Run 'pip install spidev' on the target board.")
            log.warning("=" * 60)
            self.is_mock = True
        except PermissionError as pe:
            log.error("=" * 60)
            log.error("SPI PERMISSION DENIED: Unable to open %s", dev_path)
            log.error("Details: %s", pe)
            log.error("💡 Solution: Execute 'sudo chmod 666 %s' and restart.", dev_path)
            log.error("=" * 60)
            self.is_mock = True
        except Exception as e:
            log.error("=" * 60)
            log.error("SPI INITIALIZATION FAILED UNEXPECTEDLY:")
            log.error("Details: %s", e)
            log.error("Running in MOCK mode.")
            log.error("=" * 60)
            self.is_mock = True

    def write_leds(self, colors: list[tuple[int, int, int]]) -> None:
        """Write color stream to WS2812B strip via SPI.

        Parameters
        ----------
        colors : list of (R, G, B) tuples, length must equal self.num_leds.
        """
        if len(colors) != self.num_leds:
            raise ValueError(f"Colors list size ({len(colors)}) must match configured LED count ({self.num_leds})")

        if self.is_mock:
            return

        tx_buffer = []
        for r, g, b in colors:
            # WS2812B uses GRB format
            for val in (g, r, b):
                for bit in range(7, -1, -1):
                    if (val >> bit) & 1:
                        # Data '1' wave (long High, short Low) -> 0b11111100
                        tx_buffer.append(0b11111100)
                    else:
                        # Data '0' wave (short High, long Low) -> 0b11000000
                        tx_buffer.append(0b11000000)

        with self.lock:
            if self.spi is not None:
                self.spi.xfer2(tx_buffer)
                # WS2812B reset latch timing (minimum 50us, 100us is safe)
                time.sleep(0.0001)

    def set_state(self, state: LightState) -> bool:
        """Set lighting state. Uses caching to prevent redundant SPI transactions.

        Parameters
        ----------
        state : LightState
            The target state to transition to.

        Returns
        -------
        bool : True if state actually changed, False if skipped due to cache hit.
        """
        # Lock during state check and update to avoid race conditions
        with self.lock:
            if self.current_state == state:
                return False
            self.current_state = state

        # Determine target color based on Scanner scenario
        if state == LightState.READY:
            # [상태 1] READY: Soft Green (R:0, G:40, B:0)
            color = (0, 40, 0)
        elif state == LightState.SCANNING:
            # [상태 2] SCANNING: Bright White (R:255, G:255, B:255)
            color = (255, 255, 255)
        elif state == LightState.COMPLETE:
            # [상태 3] COMPLETE: Blue Feedback (R:0, G:0, B:150)
            color = (0, 0, 150)
        else:
            color = (0, 0, 0)

        log.info("[LED State Transition] %s -> Color: %s", state.name, color)
        colors = [color] * self.num_leds
        self.write_leds(colors)
        return True

    def close(self) -> None:
        """Clean up SPI device and black out LEDs for protection."""
        log.info("Blacking out LEDs and closing SPI port.")
        try:
            self.write_leds([(0, 0, 0)] * self.num_leds)
        except Exception:
            pass
        
        with self.lock:
            if self.spi is not None:
                self.spi.close()
                self.spi = None
