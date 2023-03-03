"""
export EPICS_CA_AUTO_ADDR_LIST=no
export EPICS_CAS_AUTO_BEACON_ADDR_LIST=no
export EPICS_CAS_BEACON_ADDR_LIST=10.66.51.255
export EPICS_CA_ADDR_LIST=10.66.51.255
"""


from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run
from caproto import ChannelType
import asyncio
import zmq.asyncio
import zmq
from textwrap import dedent
import json

class ADR(PVGroup):
    """
    A class to read temperatures from NIST's adr_gui
    """
    TEMP = pvproperty(value=0.0, record='ai', doc="temperature in k")
    TEMP_SP = pvproperty(value=0.050, record='ai', doc="temperature setpoint")
    TEMP_SP_RB = pvproperty(value=0.0, record='ai', doc='temperature setpoint readback')
    TEMP_RMS_UK = pvproperty(value=0.0, record='ai', doc="temperature rms stability in uk")
    ALT_TEMP = pvproperty(value=0.0, record='ai', doc="2nd channel temperature")
    HEATER_OUT = pvproperty(value=0.0, record='ai', doc="heater")
    STATE = pvproperty(value="", dtype=str, report_as_string=True, doc="ADR Mode")
    CYCLE_UID = pvproperty(value="", dtype=str, report_as_string=True, doc="Cycle UID")
    PAUSE = pvproperty(value=0, doc="Pause PID Loop")
    START_CYCLE = pvproperty(value=0, doc="Start Cryo Cycle")
    update_hook = pvproperty(value=False, name="update")

    def __init__(self, *args, address="10.66.48.41", sub_port=5021, control_port=5020, **kwargs):
        self.address = address
        self.sub_port = sub_port
        self.control_port = control_port
        self.ctx = zmq.asyncio.Context()
        self.socket = self.ctx.socket(zmq.SUB)
        self.socket.connect(f"tcp://{self.address}:{self.sub_port}")
        self.socket.subscribe("")
        super().__init__(*args, **kwargs)

    async def command(self, method, *args, **kwargs):
        ctx = zmq.asyncio.Context()
        control_socket = ctx.socket(zmq.REQ)
        addr = f"tcp://{self.address}:{self.control_port}"
        control_socket.connect(addr)
        msg = json.dumps({'method': method, 'params': args, 'kwargs': kwargs})
        # print(addr, msg)
        await control_socket.send(msg.encode())
        control_socket.close()
        
    @PAUSE.putter
    async def PAUSE(self, instance, value):
        if value == 1:
            await self.command('pausePID')
        else:
            await self.command('resumePID')

    @START_CYCLE.putter
    async def START_CYCLE(self, instance, value):
        if value:
            await self.command('start_mag_cycle')

    @TEMP_SP.putter
    async def TEMP_SP(self, instance, value):
        await self.command('set_temp_sp_k', value)
        
    @update_hook.scan(period=0.1)
    async def update_hook(self, instance, async_lib):
        msg = await self.socket.recv_json()
        for k, v in msg.items():
            if k == 'temperature':
                await self.TEMP.write(v)
            elif k == 'alt_temp':
                await self.ALT_TEMP.write(v)
            elif k == 'state':
                if v != self.STATE.value:
                    await self.STATE.write(v)
            elif k == 'heater':
                await self.HEATER_OUT.write(v)
            elif k == 'stddev':
                await self.TEMP_RMS_UK.write(v)
            elif k == "uid":
                if v != self.CYCLE_UID.value:
                    await self.CYCLE_UID.write(v)
            elif k == 'temp_sp_rb':
                await self.TEMP_SP_RB.write(v)

if __name__ == "__main__":
    ioc_options, run_options = ioc_arg_parser(default_prefix="XF:07ID-ES{{UCAL:ADR}}:",
                                              desc = dedent(ADR.__doc__),
                                              supported_async_libs=('asyncio',))
    ioc = ADR(**ioc_options)
    run(ioc.pvdb, **run_options)
