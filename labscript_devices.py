#####################################################################
#                                                                   #
# Red Pitaya PID (pyrpl) labscript device                           #
#                                                                   #
#####################################################################
print("Loading Red Pitaya PID labscript device...")

from labscript import Device
from labscript.labscript import set_passed_properties


class red_pitaya_pyrpl_pid(Device):
    """Labscript device for configuring Red Pitaya PID via pyrpl.

    Writes static parameters to the shot file for the worker to apply.
    """

    description = 'Red Pitaya PID (pyrpl) - user variant'
    allowed_children = []

    @set_passed_properties(
        {'connection_table_properties': ['ip_addr'],}
    )
    def __init__(self, name, ip_addr, parent_device=None, **kwargs):
        Device.__init__(self, name, parent_device, connection=None, **kwargs)
        self.BLACS_connection = ip_addr

        # Start empty; channels/keys are created lazily by the setters
        self.pid_params = {}  # or: defaultdict(dict)

    def set_setpoint_array(self, channel='in1', array=None, key='digital_setpoint_array'):
        """
        Set an array parameter for a channel (default key: 'digital_setpoint_array').
        Creates the channel on demand.
        """
        if array is None:
            array = [0.0] * 16
        if len(array) > 16:
            print('Warning: Setpoint array has more than 16 elements. Only the first 16 will be used.')
            array = list(array[:16])
        if len(array) < 16:
            array = list(array) + [0.0] * (16 - len(array))

        ch = self.pid_params.setdefault(channel, {})
        ch[key] = list(array)


    def generate_code(self, hdf5_file):
        """Write PID parameters to HDF5 file"""
        Device.generate_code(self, hdf5_file)
        grp = hdf5_file.require_group(f'/devices/{self.name}/')

        for channel, params in self.pid_params.items():
            channel_grp = grp.require_group(channel)
            for key, value in params.items():
                if isinstance(value, str):
                    ds = channel_grp.require_dataset(key, (), dtype='S64')  # a bit more room than S32
                    ds[()] = value.encode('utf-8')
                elif isinstance(value, (list, tuple)):
                    import numpy as np
                    arr = np.array(value, dtype=float)
                    ds = channel_grp.require_dataset(key, arr.shape, dtype='f')
                    ds[...] = arr
                elif isinstance(value, bool):
                    ds = channel_grp.require_dataset(key, (), dtype='?')
                    ds[()] = bool(value)
                else:
                    ds = channel_grp.require_dataset(key, (), dtype='f')
                    ds[()] = float(value)
