from __future__ import annotations

from sim.machines.base import Machine


class HydraulicPress(Machine):
    asset_type = "hydraulic_press"

    def _demand(self) -> float:
        return self.load * self.speed + 0.15 * self.damage("pump") + 0.1 * self.damage("seal")

    def _signals(self, dt: float) -> dict[str, float]:
        p, run, load, speed = self.p, self.running, self.load, self.speed
        d_pump, d_seal = self.damage("pump"), self.damage("seal")
        d_oil, d_valve = self.damage("oil"), self.damage("valve")
        pressure = p["pressure_bar"] * (0.6 + 0.4 * load) * (1 - p["seal_pressure_loss"] * d_seal)
        pressure -= p["pump_pressure_loss_bar"] * d_pump
        heat = (
            p["oil_temp_rise_c"] * load
            + p["oil_damage_temp_c"] * d_oil
            + p["oil_pump_temp_c"] * d_pump
        )
        return {
            "pump.flow": p["flow_l_min"] * speed * (1 - p["pump_flow_loss"] * d_pump),
            "pump.pressure": pressure * run,
            "oil.temp": self.lag("oil", self.ambient_c + heat * run, p["oil_tau_s"], dt),
            "valve.switch_time": p["valve_ms"] + p["valve_damage_ms"] * d_valve**1.5,
            "motor.current": self.electrical.current_a,
            "ram.cycle_count": float(self.counter.total),
        }
