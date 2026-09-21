from __future__ import annotations

from sim.machines.base import Machine


class Compressor(Machine):
    asset_type = "compressor"

    def _demand(self) -> float:
        return (
            self.load * (1 + 0.3 * self.damage("valve"))
            + 0.1 * self.damage("filter")
            + 0.05 * self.damage("bearing")
        )

    def _signals(self, dt: float) -> dict[str, float]:
        p, run, load = self.p, self.running, self.load
        d_bearing, d_airend = self.damage("bearing"), self.damage("airend")
        d_valve, d_filter = self.damage("valve"), self.damage("filter")
        pressure = (
            p["pressure_bar"] * (0.85 + 0.15 * load) * (1 - p["valve_pressure_loss"] * d_valve)
        )
        pressure -= p["filter_pressure_loss_bar"] * d_filter
        heat = (
            p["temp_rise_c"] * load + p["airend_temp_c"] * d_airend + p["filter_temp_c"] * d_filter
        )
        vib = p["vib_base"] + p["vib_load"] * load + p["vib_damage"] * d_bearing**2
        dp = (p["filter_dp_base_bar"] + p["filter_dp_damage_bar"] * d_filter**1.5) * (
            0.5 + 0.5 * load
        )
        return {
            "bearing.vib_rms": vib if run else p["vib_idle"],
            "airend.discharge_pressure": self.lag(
                "pressure", pressure * run, p["pressure_tau_s"], dt
            ),
            "airend.discharge_temp": self.lag(
                "airend", self.ambient_c + heat * run, p["temp_tau_s"], dt
            ),
            "filter.dp": dp * run,
            "motor.current": self.electrical.current_a,
        }
