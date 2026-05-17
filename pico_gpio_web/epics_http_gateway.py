#!/usr/bin/env python3
"""EPICS CA gateway for Pico W HTTP control.

This IOC runs on PC and bridges EPICS PVs to the Pico W MicroPython server.
Pico side: http://192.168.3.100 (picow_main.py)

Required packages:
  pip install caproto

Run:
  python arduino-apps/pico_gpio_web/epics_http_gateway.py

PV examples:
  caget PICO:FREQ_SET
  caput PICO:FREQ_SET 10
  caput PICO:RUN_CMD 0
  camonitor PICO:VOLT_RBV
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error

from caproto.server import PVGroup, pvproperty, ioc_arg_parser, run


PICO_BASE_URL = "http://192.168.3.100"
REQ_TIMEOUT = 1.5


def http_get_text(path: str) -> str:
    url = PICO_BASE_URL + path
    with urllib.request.urlopen(url, timeout=REQ_TIMEOUT) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def pico_set_freq(freq_hz: float) -> None:
    http_get_text(f"/set?freq={freq_hz:.3f}")


def pico_stop() -> None:
    http_get_text("/stop")


def pico_status() -> dict:
    raw = http_get_text("/status")
    return json.loads(raw)


class PicoGatewayIOC(PVGroup):
    # Writable control PVs
    freq_set = pvproperty(value=1.0, dtype=float, record="ao", doc="Set output frequency [Hz]")
    run_cmd = pvproperty(value=0, dtype=int, record="bo", doc="1: run, 0: stop")

    # Readback/monitor PVs
    freq_rbv = pvproperty(value=0.0, dtype=float, read_only=True, record="ai", doc="Readback frequency [Hz]")
    volt_rbv = pvproperty(value=0.0, dtype=float, read_only=True, record="ai", doc="GP26 voltage [V]")
    pin_rbv = pvproperty(value=0, dtype=int, read_only=True, record="bi", doc="GP15 pin state")
    alive = pvproperty(value=0, dtype=int, read_only=True, record="bi", doc="1 when Pico is reachable")

    @freq_set.putter
    async def freq_set(self, instance, value):
        value = max(0.1, min(float(value), 10000.0))
        try:
            pico_set_freq(value)
            await self.freq_rbv.write(value)
            await self.run_cmd.write(1)
            await self.alive.write(1)
        except Exception:
            await self.alive.write(0)
        return value

    @run_cmd.putter
    async def run_cmd(self, instance, value):
        v = 1 if int(value) else 0
        try:
            if v == 0:
                pico_stop()
                await self.freq_rbv.write(0.0)
                await self.alive.write(1)
            else:
                target = float(self.freq_set.value)
                if target <= 0:
                    target = 1.0
                pico_set_freq(target)
                await self.freq_rbv.write(target)
                await self.alive.write(1)
        except Exception:
            await self.alive.write(0)
        return v

    @alive.scan(period=2.0)
    async def alive(self, instance, async_lib):
        try:
            st = pico_status()
            freq = float(st.get("freq", 0.0))
            volt = float(st.get("volt", 0.0))
            pin = int(st.get("pin", 0))

            await self.freq_rbv.write(freq)
            await self.volt_rbv.write(volt)
            await self.pin_rbv.write(pin)
            await self.run_cmd.write(1 if freq > 0 else 0)
            await self.alive.write(1)
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError):
            await self.alive.write(0)


def main() -> None:
    ioc_options, run_options = ioc_arg_parser(
        default_prefix="PICO:",
        desc="Pico W HTTP to EPICS CA gateway IOC",
    )
    ioc = PicoGatewayIOC(**ioc_options)
    run(ioc.pvdb, **run_options)


if __name__ == "__main__":
    main()
