from __future__ import annotations

from sim.machines.base import Machine
from sim.physics import TaylorToolLife


class CncMill(Machine):
    asset_type = "cnc_mill"

    def _demand(self) -> float:
        return (
            self.load * self.speed**0.5 + 0.08 * self.damage("spindle") + 0.05 * self.damage("axis")
        )

    def _signals(self, dt: float) -> dict[str, float]:
        p, run, load, speed = self.p, self.running, self.load, self.speed
        d_spindle, d_lube = self.damage("spindle"), self.damage("lube")
        d_tool, d_axis = self.damage("tool"), self.damage("axis")
        heat = (
            p["spindle_temp_rise_c"] * load * speed
            + p["bearing_temp_c"] * d_spindle
            + p["lube_temp_c"] * d_lube
        )
        tool = self.components["tool"].process
        vib = p["vib_base"] + p["vib_load"] * load * speed**2
        vib += p["vib_damage"] * d_spindle**2 + p["vib_axis"] * d_axis**2
        return {
            "spindle.vib_rms": vib if run else p["vib_idle"],
            "spindle.vib_kurtosis": 3.0 + p["kurtosis_damage"] * d_spindle**1.5 if run else 3.0,
            "spindle.temp": self.lag(
                "spindle", self.ambient_c + heat * run, p["spindle_tau_s"], dt
            ),
            "spindle.load": 100.0 * load * (1 + 0.25 * d_tool + 0.1 * d_spindle),
            "axis.feed_rate": p["feed_rate_mm_min"] * speed * (1 - 0.15 * d_axis),
            "axis.following_error": (
                p["following_error_mm"] + p["following_error_damage_mm"] * d_axis**1.5
            )
            * run,
            "tool.wear": tool.flank_wear_mm if isinstance(tool, TaylorToolLife) else 0.0,
            "motor.current": self.electrical.current_a,
        }
