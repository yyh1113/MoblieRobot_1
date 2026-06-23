#!/usr/bin/env python3
"""
Servo Motor Controller for the D-Robotics RDK X5 using hardware PWM.

Provides thread-safe angle adjustment for servos, safe hardware resource
initialization with auto-export support, and fallback mock support when running 
on unsupported platforms or when PWM sysfs paths are not available.
"""

import logging
import os
import sys
import time
import threading

log = logging.getLogger("arducam_yolo_web")


class ServoMotorController:
    """Thread-safe hardware PWM servo controller with auto-export and mock fallback."""

    def __init__(self):
        self.lock = threading.Lock()
        self.pwm_path = None
        self.is_mock = False

        self.pwm_path = self._find_correct_pwm_path()
        if self.pwm_path is None:
            log.warning("=" * 60)
            log.warning("ACTIVE PWM CHANNEL NOT FOUND AND AUTO-EXPORT FAILED")
            log.warning("Motor controller will run in MOCK mode.")
            log.warning("💡 Solution: Make sure PWM is enabled in 'sudo srpi-config' and reboot.")
            log.warning("=" * 60)
            self.is_mock = True
            return

        self.init_pwm()

    def _find_correct_pwm_path(self) -> str | None:
        """Find the active pwm0 directory path within the system sysfs.
        Attempts to auto-export channel 0 if not already open.
        """
        base_path = "/sys/class/pwm"
        if not os.path.exists(base_path):
            return None

        try:
            chips = sorted([d for d in os.listdir(base_path) if d.startswith("pwmchip")])
            
            # 1. Search for already open pwm0 channel
            for chip in chips:
                potential_path = os.path.join(base_path, chip, "pwm0")
                if os.path.exists(potential_path):
                    log.info("[확인] 매핑된 PWM 경로를 찾았습니다: %s", potential_path)
                    return potential_path
            
            # 2. Try exporting channel 0 sequentially on found chips
            log.info("[안내] 닫혀있는 하드웨어 PWM 채널 개방(export)을 시도합니다...")
            for chip in chips:
                chip_path = os.path.join(base_path, chip)
                export_path = os.path.join(chip_path, "export")
                potential_path = os.path.join(chip_path, "pwm0")
                
                try:
                    with open(export_path, 'w') as f:
                        f.write("0")
                    time.sleep(0.5)  # Wait for kernel filesystem creation
                    
                    if os.path.exists(potential_path):
                        log.info("[확인] 새로 개방된 PWM 경로: %s", potential_path)
                        return potential_path
                except Exception:
                    pass
        except Exception as e:
            log.error("Failed to read PWM directory: %s", e)
        return None

    def _write_sysfs(self, file_name: str, value: int | str) -> None:
        """Helper to write to sysfs files."""
        if self.is_mock or not self.pwm_path:
            return
        path = os.path.join(self.pwm_path, file_name)
        with open(path, 'w') as f:
            f.write(str(value))

    def init_pwm(self) -> None:
        """Initialize hardware PWM registers to 50Hz and central duty cycle."""
        log.info("[안내] 하드웨어 PWM 초정밀 레지스터 조정을 시작합니다...")
        try:
            # Disable output first to configure period
            try:
                self._write_sysfs("enable", 0)
            except Exception:
                pass

            # 50Hz period (20ms = 20,000,000 ns)
            self._write_sysfs("period", 20000000)
            time.sleep(0.1)

            # Central position (90 degrees = 1,500,000 ns)
            self._write_sysfs("duty_cycle", 1500000)
            time.sleep(0.1)

            # Enable PWM
            self._write_sysfs("enable", 1)
            log.info("[안내] 하드웨어 PWM 초기화 완료.")
        except Exception as e:
            log.error("Failed to configure hardware PWM registers: %s", e)
            log.error("Falling back to MOCK mode.")
            self.is_mock = True

    def set_angle(self, angle: float) -> None:
        """Adjust servo angle.
        
        Parameters
        ----------
        angle : float
            Angle in degrees (0 to 180).
        """
        if angle < 0:
            angle = 0.0
        if angle > 180:
            angle = 180.0

        # Map 0..180 -> 1,400,000..1,600,000 ns (Ultra-narrow range for safety)
        pulse_ns = int(1400000 + (angle / 180.0) * 200000)

        with self.lock:
            if self.is_mock:
                log.info("[Motor MOCK] Set target angle: %.1f° -> Pulse: %d ns", angle, pulse_ns)
                return
            try:
                self._write_sysfs("duty_cycle", pulse_ns)
                log.info("[모터 제어] 목표 각도: %.1f° -> 초정밀 펄스 폭: %d ns", angle, pulse_ns)
            except Exception as e:
                log.error("[제어 오류] 각도 설정 실패: %s", e)

    def close(self) -> None:
        """Disable PWM output to protect the motor."""
        log.info("Disabling PWM output and closing motor controller.")
        with self.lock:
            try:
                self._write_sysfs("enable", 0)
            except Exception:
                pass


def main():
    import signal
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    
    controller = ServoMotorController()
    
    def sig_handler(sig, frame):
        print("\n[종료] 프로그램을 종료하고 출력을 차단합니다.")
        controller.close()
        sys.exit(0)
        
    signal.signal(signal.SIGINT, sig_handler)
    
    print("\n★ 초정밀 각도 제어 구동을 시작합니다. (종료: Ctrl+C) ★\n")
    try:
        while True:
            controller.set_angle(0)
            time.sleep(1.5)

            controller.set_angle(90)
            time.sleep(1.5)

            controller.set_angle(180)
            time.sleep(1.5)

            controller.set_angle(90)
            time.sleep(1.5)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()