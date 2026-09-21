from __future__ import annotations

from sim.machines.base import Machine


class Conveyor(Machine):
    asset_type = "conveyor"

    def _demand(self) -> float:
        return (
            self.load * self.speed
            + 0.15 * self.damage("belt")
            + 0.1 * self.damage("drive")
            + 0.05 * self.damage("bearing")
        )

    def _signals(self, dt: float) -> dict[str, float]:
        p, run, load, speed = self.p, self.running, self.load, self.speed
        d_bearing, d_drive = self.damage("bearing"), self.damage("drive")
        d_belt, d_motor = self.damage("belt"), self.damage("motor")
        vib = p["vib_base"] + p["vib_load"] * load + p["vib_damage"] * d_bearing**2
        vib += p["vib_misalign"] * d_drive**2
        axial = p["axial_base"] + p["axial_load"] * load + p["axial_damage"] * d_drive**2
        heat = p["motor_temp_rise_c"] * self._demand() + p["motor_damage_temp_c"] * d_motor
        return {
            "bearing.vib_rms": vib if run else p["vib_idle"],
            "drive.vib_axial": axial if run else p["vib_idle"],
            "belt.speed": p["belt_speed_m_s"] * speed * (1 - p["belt_slip"] * d_belt**1.2),
            "motor.current": self.electrical.current_a * (1 + 0.1 * d_motor),
            "motor.temp": self.lag("motor", self.ambient_c + heat * run, p["motor_tau_s"], dt),
        }
