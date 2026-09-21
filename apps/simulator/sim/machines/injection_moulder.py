from __future__ import annotations

from sim.machines.base import Machine

ZONE_SAG_WEIGHTS = (0.5, 0.8, 1.0)  # the zone nearest the nozzle has the most heater bands


class InjectionMoulder(Machine):
    asset_type = "injection_moulder"

    def _demand(self) -> float:
        heaters = self.p["heater_demand"] * (1 + 0.3 * self.damage("barrel"))
        return heaters + (1 - self.p["heater_demand"]) * self.load * self.speed

    def _signals(self, dt: float) -> dict[str, float]:
        p, run, load = self.p, self.running, self.load
        d_barrel, d_screw, d_clamp = (
            self.damage("barrel"),
            self.damage("screw"),
            self.damage("clamp"),
        )
        signals = {}
        for zone, weight in enumerate(ZONE_SAG_WEIGHTS, start=1):
            setpoint = p[f"zone{zone}_sp_c"]
            target = setpoint - (setpoint - self.ambient_c) * p["heater_sag"] * d_barrel * weight
            signals[f"barrel.zone{zone}_temp"] = self.lag(
                f"zone{zone}", target if run else self.ambient_c, p["barrel_tau_s"], dt
            )
        injection = p["injection_pressure_bar"] * (0.8 + 0.2 * load)
        clamp = p["clamp_force_kn"] * (0.9 + 0.1 * load)
        cycle_energy_wh = self.electrical.power_kw * self.counter.cycle_time_s / 3.6
        signals |= {
            "screw.injection_pressure": injection * (1 - p["screw_pressure_loss"] * d_screw) * run,
            "clamp.force": clamp * (1 - p["clamp_loss"] * d_clamp) * run,
            "drive.current": self.electrical.current_a,
            "drive.cycle_energy": cycle_energy_wh * run,
        }
        return signals
