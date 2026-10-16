"""
PLC Slave — Modbus TCP server simulating a water treatment plant PLC.

Runs a pymodbus async server with a background process simulation loop that
updates input registers and discrete inputs based on the process model, while
holding registers and coils are writable by SCADA (or attackers).

Ported to pymodbus 3.x native SimDevice/SimData API.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pymodbus.server import StartAsyncTcpServer
from pymodbus.simulator.simdata import DataType, SimData
from pymodbus.simulator.simdevice import SimDevice

from ot_twin.config import PLC_HOST, PLC_PORT, PLC_UNIT_ID, PROCESS_TICK_SECONDS
from ot_twin.environment.process_model import WaterTreatmentProcess
from ot_twin.environment.register_map import (
    COILS,
    DISCRETE_INPUTS,
    HOLDING_REGISTERS,
    INPUT_REGISTERS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal register store — plain Python dicts keyed by address.
# pymodbus 3.x action callbacks read/write these directly.
# ---------------------------------------------------------------------------
_coils: dict[int, bool] = {}
_discrete_inputs: dict[int, bool] = {}
_holding_registers: dict[int, int] = {}
_input_registers: dict[int, int] = {}


def _init_stores() -> None:
    """Populate register stores with default values from the register map."""
    for entry in COILS:
        _coils[entry.address] = bool(int(entry.default_value))
    for entry in DISCRETE_INPUTS:
        _discrete_inputs[entry.address] = bool(int(entry.default_value))
    for entry in HOLDING_REGISTERS:
        _holding_registers[entry.address] = int(entry.default_value)
    for entry in INPUT_REGISTERS:
        _input_registers[entry.address] = int(entry.default_value)


# ---------------------------------------------------------------------------
# SimDevice action callback — intercepts every Modbus read/write.
# ---------------------------------------------------------------------------
async def _modbus_action(
    function_code: int,
    start_address: int,
    address: int,
    count: int,
    current_registers: list[int],
    set_values: list[int] | list[bool] | None,
) -> None:
    """
    Called by pymodbus for every request.

    - Reads  (set_values is None)  → fill current_registers from our store.
    - Writes (set_values is not None) → copy set_values into our store.

    Function codes:
      FC 1  = Read Coils
      FC 2  = Read Discrete Inputs
      FC 3  = Read Holding Registers
      FC 4  = Read Input Registers
      FC 5  = Write Single Coil
      FC 6  = Write Single Holding Register
      FC 15 = Write Multiple Coils
      FC 16 = Write Multiple Holding Registers
    """
    is_coil  = function_code in (1, 5, 15)
    is_di    = function_code == 2
    is_hr    = function_code in (3, 6, 16, 22, 23)
    is_ir    = function_code == 4

    if set_values is None:
        # --- READ ---
        for i in range(count):
            addr = address + i
            if is_coil:
                current_registers[i] = int(_coils.get(addr, False))
            elif is_di:
                current_registers[i] = int(_discrete_inputs.get(addr, False))
            elif is_hr:
                current_registers[i] = _holding_registers.get(addr, 0)
            elif is_ir:
                current_registers[i] = _input_registers.get(addr, 0)
    else:
        # --- WRITE ---
        for i, val in enumerate(set_values):
            addr = address + i
            if is_coil:
                _coils[addr] = bool(val)
            elif is_hr:
                _holding_registers[addr] = int(val)


def _build_simdevice(unit_id: int) -> SimDevice:
    """Build a SimDevice covering all four register spaces."""
    # We define one large REGISTERS block for HR (0..99) and IR (0..49),
    # and BITS blocks for Coils (0..15) and DI (0..15).
    # The action callback will serve the actual values from our dicts.
    return SimDevice(
        id=unit_id,
        action=_modbus_action,
        simdata=(
            # Coils (FC 1/5/15) — 16 bits
            [SimData(address=0, count=16, values=[False] * 16, datatype=DataType.BITS)],
            # Discrete Inputs (FC 2) — 16 bits
            [SimData(address=0, count=16, values=[False] * 16, datatype=DataType.BITS)],
            # Holding Registers (FC 3/6/16) — 100 registers
            [SimData(address=0, count=100, values=0, datatype=DataType.REGISTERS)],
            # Input Registers (FC 4) — 50 registers
            [SimData(address=0, count=50, values=0, datatype=DataType.REGISTERS)],
        ),
    )


class PLCSlave:
    """Async Modbus TCP server with integrated process simulation."""

    def __init__(
        self,
        host: str = PLC_HOST,
        port: int = PLC_PORT,
    ) -> None:
        self.host = host
        self.port = port
        self.process = WaterTreatmentProcess()
        self._running = False
        self._server_task: asyncio.Task | None = None
        self._sim_task: asyncio.Task | None = None

        # Initialise internal register stores
        _init_stores()

        # Build SimDevice (new pymodbus 3.x API)
        self._simdevice = _build_simdevice(PLC_UNIT_ID)

    async def start(self) -> None:
        """Start the PLC server and simulation loop."""
        self._running = True
        logger.info("PLC Slave starting on %s:%d", self.host, self.port)

        self._sim_task = asyncio.create_task(self._simulation_loop())

        await StartAsyncTcpServer(
            context=self._simdevice,
            address=(self.host, self.port),
        )

    async def start_background(self) -> None:
        """Start PLC in the background, returning once the server is listening."""
        self._running = True
        logger.info("PLC Slave starting (background) on %s:%d", self.host, self.port)

        self._sim_task = asyncio.create_task(self._simulation_loop())
        self._server_task = asyncio.create_task(
            StartAsyncTcpServer(
                context=self._simdevice,
                address=(self.host, self.port),
            )
        )
        # Give the server a moment to bind
        await asyncio.sleep(0.5)

    async def stop(self) -> None:
        """Stop the server and simulation."""
        self._running = False
        if self._sim_task:
            self._sim_task.cancel()
            try:
                await self._sim_task
            except asyncio.CancelledError:
                pass
        if self._server_task:
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass
        logger.info("PLC Slave stopped")

    # ------------------------------------------------------------------
    # Internal helpers — read/write our own register store directly.
    # ------------------------------------------------------------------

    def _read_coil(self, address: int) -> bool:
        return _coils.get(address, False)

    def _read_holding(self, address: int) -> int:
        return _holding_registers.get(address, 0)

    def _write_input_register(self, address: int, value: int) -> None:
        _input_registers[address] = value

    def _write_discrete_input(self, address: int, value: bool) -> None:
        _discrete_inputs[address] = value

    async def _simulation_loop(self) -> None:
        """Periodically advance the process model and sync registers."""
        while self._running:
            try:
                # Read actuator commands from coils / holding registers
                inlet_valve  = self._read_coil(0)
                outlet_valve = self._read_coil(1)
                pump_enable  = self._read_coil(2)
                mixer_enable = self._read_coil(3)
                chlorine_pump = self._read_coil(4)
                estop        = self._read_coil(5)

                inflow_sp   = self._read_holding(1)
                outflow_sp  = self._read_holding(2)
                ph_sp       = self._read_holding(3) / 100.0
                chlorine_sp = self._read_holding(4) / 100.0
                pressure_sp = self._read_holding(5)
                temp_sp     = self._read_holding(6) / 10.0

                # Tick the process model
                state = self.process.tick(
                    dt=PROCESS_TICK_SECONDS,
                    inlet_valve_open=inlet_valve,
                    outlet_valve_open=outlet_valve,
                    pump_running=pump_enable,
                    mixer_running=mixer_enable,
                    chlorine_pump_on=chlorine_pump,
                    emergency_stop=estop,
                    inflow_setpoint=float(inflow_sp),
                    outflow_setpoint=float(outflow_sp),
                    ph_setpoint=ph_sp,
                    chlorine_setpoint=chlorine_sp,
                    pressure_setpoint=float(pressure_sp),
                    temperature_setpoint=temp_sp,
                )

                # Write process values to input registers
                self._write_input_register(0, int(state.tank_level))
                self._write_input_register(1, int(state.inflow_rate))
                self._write_input_register(2, int(state.outflow_rate))
                self._write_input_register(3, int(state.ph_level * 100))
                self._write_input_register(4, int(state.chlorine_dosing * 100))
                self._write_input_register(5, int(state.turbidity * 100))
                self._write_input_register(6, int(state.pressure_psi))
                self._write_input_register(7, int(state.temperature_c * 10))

                # Write alarm states to discrete inputs
                self._write_discrete_input(0, state.high_level_alarm)
                self._write_discrete_input(1, state.low_level_alarm)
                self._write_discrete_input(2, state.ph_alarm)
                self._write_discrete_input(3, state.pressure_alarm)
                self._write_discrete_input(7, True)  # system running

                await asyncio.sleep(PROCESS_TICK_SECONDS)

            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Simulation loop error")
                await asyncio.sleep(1)
