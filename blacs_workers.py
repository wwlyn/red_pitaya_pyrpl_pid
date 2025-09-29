#####################################################################
#                                                                   #
# Red Pitaya PID (pyrpl) BLACS Worker                               #
#                                                                   #
# Based on examples from:                                            #
# - red_pitaya_pyrpl_asg_python3.7.5                                 #
# - Windfreak/RedPitayaPID                                           #
#                                                                   #
#####################################################################

print("Loading Red Pitaya PID BLACS Worker...")

import json
from blacs.tab_base_classes import Worker
import numpy as np

# calibrate the output range
OUT_MAX = 2.031
OUT_MIN = 0.007
OUT_ZERO = (OUT_MAX + OUT_MIN) / 2

ZERO_IN1 = -0.011962890625
HALF_IN1 = 0.42919921875

ZERO_IN2 = -0.0052490234375
HALF_IN2 = 0.43505859375

class red_pitaya_pyrpl_pid_worker(Worker):
    def init(self):
        import sys
        self.current = {}
        print(f"[WORKER] Worker init called.")
        print(f"[WORKER] ip_addr={getattr(self, 'ip_addr', None)}")
        print(f"[WORKER] sys.executable={sys.executable}")
        try:
            import numpy as np
            if not hasattr(np, 'VisibleDeprecationWarning'):
                np.VisibleDeprecationWarning = UserWarning
            if not hasattr(np, 'ComplexWarning'):
                np.ComplexWarning = UserWarning
            if not hasattr(np, "complex"):
                np.complex = complex
            from pyrpl import Pyrpl
            print("[WORKER] Imported Pyrpl successfully.")
            print(f"[WORKER] Attempting to connect to Red Pitaya at {self.ip_addr}")
            self.p = Pyrpl(hostname=self.ip_addr)
            print("[WORKER] Pyrpl instance created successfully.")
            # Always use pid1 by default, so that it's easier to write analogous code for pid0
            self.pids = {
                'in2': self.p.rp.pid0,
                'in1': self.p.rp.pid1
            }
            self.pids['in1'].ival = -0.99
            self.pids['in2'].ival = -0.99
            self.pids['in1'].pause_gains = 'pi'
            self.pids['in2'].pause_gains = 'pi'
            self.pids['in1'].paused = True
            self.pids['in2'].paused = True
            if 'blacs' in self.p.c._keys():
                blacs_cfg = self.p.c['blacs']
                self.pids['in1'].input = blacs_cfg['in1_input']
                self.pids['in2'].input = blacs_cfg['in2_input']
                self.pids['in1'].output_direct = blacs_cfg['in1_output_direct']
                self.pids['in2'].output_direct = blacs_cfg['in2_output_direct']
                self.pids['in1'].differential_mode_enabled = blacs_cfg['in1_differential_mode']
                self.pids['in2'].differential_mode_enabled = blacs_cfg['in2_differential_mode']
                self.pids['in1'].setpoint = blacs_cfg['in1_setpoint']
                self.pids['in2'].setpoint = blacs_cfg['in2_setpoint']
                self.pids['in1'].pause_gains = blacs_cfg['in1_pause_gains']
                self.pids['in2'].pause_gains = blacs_cfg['in2_pause_gains']
                self.pids['in1'].max_voltage = blacs_cfg['in1_max_voltage']
                self.pids['in2'].max_voltage = blacs_cfg['in2_max_voltage']
                self.pids['in1'].min_voltage = blacs_cfg['in1_min_voltage']
                self.pids['in2'].min_voltage = blacs_cfg['in2_min_voltage']
                self.pids['in1'].ival = blacs_cfg['in1_ival']
                self.pids['in2'].ival = blacs_cfg['in2_ival']
                self.pids['in1'].p = blacs_cfg['in1_p']
                self.pids['in2'].p = blacs_cfg['in2_p']
                self.pids['in1'].i = blacs_cfg['in1_i']
                self.pids['in2'].i = blacs_cfg['in2_i']
                self.pids['in1'].use_setpoint_sequence = blacs_cfg['in1_use_setpoint_sequence']
                self.pids['in2'].use_setpoint_sequence = blacs_cfg['in2_use_setpoint_sequence']
                self.pids['in1'].setpoint_index = blacs_cfg['in1_setpoint_index']
                self.pids['in2'].setpoint_index = blacs_cfg['in2_setpoint_index']
                in1_digital_setpoint_array = blacs_cfg['in1_digital_setpoint_array']
                in2_digital_setpoint_array = blacs_cfg['in2_digital_setpoint_array']
                self.pids['in1'].set_setpoint_array(in1_digital_setpoint_array)
                self.pids['in2'].set_setpoint_array(in2_digital_setpoint_array)
                # Initialize current dictionary structure before accessing
                self.current['in1'] = {}
                self.current['in2'] = {}
                self.current['in1']['digital_setpoint_array'] = [self.dig2phy_setpoint_in1(x) for x in in1_digital_setpoint_array]
                self.current['in2']['digital_setpoint_array'] = [self.dig2phy_setpoint_in2(x) for x in in2_digital_setpoint_array]
                if blacs_cfg['set_in2_enabled']:
                    self.setpoint_source = 'digital_setpoint_in2'
                    self.set_in2_enabled = True
                    self.set_analog_enabled = False
                    self.set_in1_enabled = blacs_cfg['set_in1_enabled']
                if blacs_cfg['set_in1_enabled']:
                    self.setpoint_source = 'digital_setpoint_in1'
                    self.set_in1_enabled = True
                    self.set_analog_enabled = False
                    self.set_in2_enabled = blacs_cfg['set_in2_enabled']
                if blacs_cfg['set_analog_enabled']:
                    self.setpoint_source = 'analog_setpoint'
                    self.set_analog_enabled = True
                    self.set_in2_enabled = False
                    self.set_in1_enabled = False
            else:
                self.setpoint_source = 'digital_setpoint_in1'
                self.pids['in1'].input = 'in1'
                self.pids['in1'].output_direct = 'out1'
                self.pids['in2'].input = 'in2'
                self.pids['in2'].output_direct = 'out2'
                self.set_in1_enabled = True
                self.set_in2_enabled = False
                self.set_analog_enabled = False
        except Exception as e:
            print(f"[WORKER] Pyrpl connection failed: {e}, please read logs for more details.")
            import traceback
            traceback.print_exc()
            raise

    # ---------- Individual Parameter Setting Methods (Windfreak style) ----------
    def _get_pid(self, pid_id):
        """Helper to get the correct PID instance based on ID."""
        if pid_id not in self.pids:
            raise ValueError(f"Invalid PID ID: {pid_id}. Must be 0 or 1.")
        return self.pids[pid_id]
    
    def set_p(self, value):
        """Set P parameter directly"""        
        try:
            if self.setpoint_source == 'digital_setpoint_in2':
                self._set_param('in2', 'p', value)
                return float(self._get_pid('in2').p)
            else:
                self._set_param('in1', 'p', value)
                return float(self._get_pid('in1').p)
        except Exception as e:
            print(f"[DEBUG] set_p error: {e}")
            raise

    def set_i(self, value):
        """Set I parameter directly"""
        try:
            if self.setpoint_source == 'digital_setpoint_in2':
                self._set_param('in2', 'i', value)
                return float(self._get_pid('in2').i)
            else:
                self._set_param('in1', 'i', value)
                return float(self._get_pid('in1').i)
        except Exception as e:
            print(f"[DEBUG] set_i error: {e}")
            raise

    def set_setpoint(self, value):
        """Set setpoint parameter directly"""
        try:
            if self.setpoint_source == 'digital_setpoint_in2':
                self._set_param('in2', 'setpoint', self.phy2dig_setpoint_in2(value))
                return self.dig2phy_setpoint_in2(float(self._get_pid('in2').setpoint))
            else:
                self._set_param('in1', 'setpoint', self.phy2dig_setpoint_in1(value))
                return self.dig2phy_setpoint_in1(float(self._get_pid('in1').setpoint))
        except Exception as e:
            print(f"[DEBUG] set_setpoint error: {e}")
            raise

    def set_output_direct(self, output_value):
        """Set the direct output parameter."""
        try:
            if self.setpoint_source == 'digital_setpoint_in2':
                self._set_param('in2', 'output_direct', output_value)
                return self._get_pid('in2').output_direct
            else:
                self._set_param('in1', 'output_direct', output_value)
                return self._get_pid('in1').output_direct
        except Exception as e:
            print(f"[DEBUG] set_output_direct error: {e}")
            raise

    def set_input(self, value):
        """Set input parameter directly"""
        try:
            if self.setpoint_source == 'digital_setpoint_in2':
                self._set_param('in2', 'input', value)
                return self._get_pid('in2').input
            else:
                self._set_param('in1', 'input', value)
                return self._get_pid('in1').input
        except Exception as e:
            print(f"[DEBUG] set_input error: {e}")
            raise

    def set_min_voltage(self, value):
        """Set min_voltage parameter directly"""
        try:
            if self.setpoint_source == 'digital_setpoint_in2':
                self._set_param('in2', 'min_voltage', value)
                return float(self._get_pid('in2').min_voltage)
            else:
                self._set_param('in1', 'min_voltage', value)
                return float(self._get_pid('in1').min_voltage)
        except Exception as e:
            print(f"[DEBUG] set_min_voltage error: {e}")
            raise

    def set_max_voltage(self, value):
        """Set max_voltage parameter directly"""
        try:
            if self.setpoint_source == 'digital_setpoint_in2':
                self._set_param('in2', 'max_voltage', value)
                return float(self._get_pid('in2').max_voltage)
            else:
                self._set_param('in1', 'max_voltage', value)
                return float(self._get_pid('in1').max_voltage)
        except Exception as e:
            print(f"[DEBUG] set_max_voltage error: {e}")
            raise

    def set_ival(self, value):
        """Set ival parameter directly"""
        try:
            if self.setpoint_source == 'digital_setpoint_in2':
                self._set_param('in2', 'ival', value)
                return float(self._get_pid('in2').ival)
            else:
                self._set_param('in1', 'ival', value)
                print(f"[DEBUG] set_ival: {value}")
                return float(self._get_pid('in1').ival)
                
        except Exception as e:
            print(f"[DEBUG] set_ival error: {e}")
            raise

    def enable_pid(self):
        """Enable the PID controller"""
        try:
            if self.setpoint_source == 'digital_setpoint_in2':
                self._set_param('in2', 'paused', False)
                self.set_in2_enabled = True
                self.set_analog_enabled = False
                return not self._get_pid('in2').paused
            elif self.setpoint_source == 'digital_setpoint_in1':
                self._set_param('in1', 'paused', False)
                self.set_in1_enabled = True
                self.set_analog_enabled = False
                return not self._get_pid('in1').paused
            elif self.setpoint_source == 'analog_setpoint':
                self._set_param('in1', 'paused', False)
                self.set_analog_enabled = True
                self.set_in1_enabled = False
                self.set_in2_enabled = False
                return not self._get_pid('in1').paused
        except Exception as e:
            print(f"[DEBUG] enable_pid error: {e}")
            raise

    def disable_pid(self):
        """Disable the PID controller"""
        try:
            if self.setpoint_source == 'digital_setpoint_in2':
                self._set_param('in2', 'paused', True)
                self.set_in2_enabled = False
                return self._get_pid('in2').paused
            elif self.setpoint_source == 'digital_setpoint_in1':
                self._set_param('in1', 'paused', True)
                self.set_in1_enabled = False
                return self._get_pid('in1').paused
            elif self.setpoint_source == 'analog_setpoint':
                self._set_param('in1', 'paused', True)
                self.set_analog_enabled = False
                return self._get_pid('in1').paused
        except Exception as e:
            print(f"[DEBUG] disable_pid error: {e}")
            raise

    def set_pause_gains(self, value):
        """Set pause_gains parameter directly"""
        try:
            if self.setpoint_source == 'digital_setpoint_in2':
                self._set_param('in2', 'pause_gains', value)
                return self._get_pid('in2').pause_gains
            else:
                self._set_param('in1', 'pause_gains', value)
                return self._get_pid('in1').pause_gains
        except Exception as e:
            print(f"[WORKER] set_pause_gains error: {e}")
            raise

    def set_setpoint_source(self, value):
        """Set setpoint source (analog_setpoint or digital_setpoint)"""
        print(f"[WORKER] Setting setpoint source to: {value}")
        self.current['setpoint_source'] = value
        self.setpoint_source = value
        if value == 'analog_setpoint':
            self.set_in1_enabled = False
            self.set_in2_enabled = False
            self.set_analog_enabled = True
            self.pids['in1'].use_setpoint_sequence = False
            self.pids['in2'].use_setpoint_sequence = False
            self.setpoint_source = 'analog_setpoint'
            self.pids['in2'].output_direct = 'off'
            self.pids['in1'].output_direct = 'out1'
            self.pids['in1'].input = 'in1'
            self.pids['in2'].input = 'in2'
            self.pids['in1'].setpoint = 0 #dummy
            self.pids['in2'].setpoint = 0 #dummy
            self.pids['in1'].p = 0
            self.pids['in1'].i = 0
            self.pids['in1'].ival = 0
            self.pids['in2'].p = 0
            self.pids['in2'].i = 0
            self.pids['in2'].ival = 0
            self.pids['in2'].max_voltage = 0.99
            self.pids['in2'].min_voltage = -0.99
            self.pids['in1'].pause_gains = "pi"
            self.pids['in2'].pause_gains = "pi"
            self.pids['in2'].paused = True
            self.pids['in1'].paused = True
            self.pids['in1'].differential_mode_enabled = True
            self._read_current_state()
            print(f"[WORKER] set_setpoint_source: analog_setpoint mode enabled, input is in1, setpoint is in2, output is out1!")
        elif value == 'digital_setpoint_in1':
            self.set_in1_enabled = True
            self.set_analog_enabled = False
            self.setpoint_source = 'digital_setpoint_in1'
            self.pids['in1'].input = 'in1'
            self.pids['in1'].output_direct = 'out1'
            self.pids['in1'].differential_mode_enabled = False
            self.pids['in2'].differential_mode_enabled = False
            self._read_current_state()
            print(f"[WORKER] set_setpoint_source: digital_setpoint mode, PID values refreshed: {self.current}")
        elif value == 'digital_setpoint_in2':
            self.set_in2_enabled = True
            self.set_analog_enabled = False
            self.setpoint_source = 'digital_setpoint_in2'
            self.pids['in2'].input = 'in2'
            self.pids['in2'].output_direct = 'out2'
            self.pids['in1'].differential_mode_enabled = False
            self.pids['in2'].differential_mode_enabled = False
            self._read_current_state()
            print(f"[WORKER] set_setpoint_source: digital_setpoint_in2 mode, PID values refreshed: {self.current}")
        return value

    def _read_current_state(self):
        """Read the current state of both PID modules from hardware."""
        status = {}
        try:
            for pid_id, pid in self.pids.items():
                if pid_id == 'in1':
                    setpoint_phy = self.dig2phy_setpoint_in1(pid.setpoint)
                    setpoint_in_sequence_phy = self.dig2phy_setpoint_in1(pid.setpoint_in_sequence)
                else:
                    setpoint_phy = self.dig2phy_setpoint_in2(pid.setpoint)
                    setpoint_in_sequence_phy = self.dig2phy_setpoint_in2(pid.setpoint_in_sequence)
                pid_status = {
                    'input': pid.input,
                    'output_direct': pid.output_direct,
                    'setpoint': setpoint_phy,
                    'p': pid.p,
                    'i': pid.i,
                    'max_voltage': pid.max_voltage+OUT_ZERO,
                    'min_voltage': pid.min_voltage+OUT_ZERO,
                    'ival': pid.ival,
                    'pause_gains': pid.pause_gains,
                    'paused': pid.paused,
                    'differential_mode_enabled': pid.differential_mode_enabled,
                    'use_setpoint_sequence': pid.use_setpoint_sequence,
                    'setpoint_index': pid.setpoint_index,
                    'setpoint_in_sequence': setpoint_in_sequence_phy,
                    'sequence_wrap_flag': pid.sequence_wrap_flag,
                    # Preserve existing digital_setpoint_array if it exists
                    'digital_setpoint_array': self.current.get(pid_id, {}).get('digital_setpoint_array', [])
                }
                status[pid_id] = pid_status
            
            print(f"[WORKER] Current state for all PIDs read successfully: {status}")
            # Update instead of replace to preserve initialization data
            self.current.update(status)
        except Exception as e:
            print(f"[WORKER] Error reading current state: {e}")

    def _set_param(self, pid_id, name, value):
        """Helper to set a parameter for a specific PID module."""
        pid = self._get_pid(pid_id)
        print(f"[DEBUG] _set_param called for PID{pid_id}: {name} = {value}")
        try:
            if name == 'input':
                pid.input = value
            elif name == 'output_direct':
                pid.output_direct = value
            elif name == 'setpoint':
                pid.setpoint = float(value)
            elif name == 'p':
                pid.p = float(value)
            elif name == 'i':
                pid.i = float(value)
            elif name == 'ival':
                pid.ival = float(value)
            elif name == 'max_voltage':
                pid.max_voltage = float(value)
                self.current[pid_id]['max_voltage'] = pid.max_voltage + OUT_ZERO
            elif name == 'min_voltage':
                pid.min_voltage = float(value)
                self.current[pid_id]['min_voltage'] = pid.min_voltage + OUT_ZERO
            elif name == 'pause_gains':
                pid.pause_gains = value
            elif name == 'paused':
                pid.paused = bool(value)
            elif name == 'differential_mode_enabled':
                pid.differential_mode_enabled = bool(value)
            else:
                raise ValueError(f'Unknown PID parameter: {name}')
            print(f"[DEBUG] _set_param success for PID{pid_id}: {name} set to {value}")
        except Exception as e:
            print(f"[DEBUG] _set_param error for PID{pid_id}: {name} = {value}, error: {e}")
            raise
        if name != 'max_voltage' and name != 'min_voltage':
            self.current[pid_id][name] = value
    
    def reset_pid(self):
        try:
            if self.setpoint_source == 'digital_setpoint_in2':
                self._set_param('in2', 'p', 0.0)
                self._set_param('in2', 'i', 0.0)
                self._set_param('in2', 'ival', 0.0)
                self._set_param('in2', 'setpoint', self.phy2dig_setpoint_in2(0.0))
                self.set_setpoint_array(np.zeros(16))
                return f"PID reset: p={self.pids['in2'].p}, i={self.pids['in2'].i}, ival={self.pids['in2'].ival}, setpoint={self.pids['in2'].setpoint}"
            else:
                self._set_param('in1', 'i', 0.0)
                self._set_param('in1', 'p', 0.0)
                self._set_param('in1', 'ival', 0.0)
                self._set_param('in1', 'setpoint', self.phy2dig_setpoint_in1(0.0))
                self.set_setpoint_array(np.zeros(16))
                return f"PID reset: p={self.pids['in1'].p}, i={self.pids['in1'].i}, ival={self.pids['in1'].ival}, setpoint={self.pids['in1'].setpoint}"
        except Exception as e:
            print(f"[WORKER] reset_pid error: {e}")
            return f"Reset failed: {e}"

    # ---------- Methods callable from the Tab ----------
    def write_to_config(self):
        import yaml
        import shutil
        path = self.p.c._filename
        with open(path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        config['blacs'] = {
            'set_analog_enabled': bool(self.set_analog_enabled),
            'set_in1_enabled': bool(self.set_in1_enabled),
            'set_in2_enabled': bool(self.set_in2_enabled),
            'in1_p': float(self.pids['in1'].p),
            'in2_p': float(self.pids['in2'].p),
            'in1_i': float(self.pids['in1'].i),
            'in2_i': float(self.pids['in2'].i),
            'in1_ival': float(self.pids['in1'].ival),
            'in2_ival': float(self.pids['in2'].ival),
            'in1_differential_mode': bool(self.pids['in1'].differential_mode_enabled),
            'in2_differential_mode': bool(self.pids['in2'].differential_mode_enabled),
            'in1_input': str(self.pids['in1'].input),
            'in2_input': str(self.pids['in2'].input),
            'in1_output_direct': str(self.pids['in1'].output_direct),
            'in2_output_direct': str(self.pids['in2'].output_direct),
            'in1_max_voltage': float(self.pids['in1'].max_voltage),
            'in2_max_voltage': float(self.pids['in2'].max_voltage),
            'in1_min_voltage': float(self.pids['in1'].min_voltage),
            'in2_min_voltage': float(self.pids['in2'].min_voltage),
            'in1_pause_gains': str(self.pids['in1'].pause_gains),
            'in2_pause_gains': str(self.pids['in2'].pause_gains),
            'in1_setpoint': float(self.pids['in1'].setpoint),
            'in2_setpoint': float(self.pids['in2'].setpoint),
            'in1_use_setpoint_sequence': bool(self.pids['in1'].use_setpoint_sequence),
            'in2_use_setpoint_sequence': bool(self.pids['in2'].use_setpoint_sequence),
            'in1_setpoint_index': int(self.pids['in1'].setpoint_index),
            'in2_setpoint_index': int(self.pids['in2'].setpoint_index),
            'in1_digital_setpoint_array': self.current.get('in1', {}).get('digital_setpoint_array', []),
            'in2_digital_setpoint_array': self.current.get('in2', {}).get('digital_setpoint_array', [])
        }
        print(config)
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True)
            

    def check_hardware_status(self):
        """Check detailed hardware status for debugging"""
        self._read_current_state()
        import time
        current_time = time.strftime("%H:%M:%S")
        print(f"[WORKER] {current_time}: Checking hardware status...")
        
        # Initialize status dictionary first
        status = {}
        
        if self.setpoint_source == 'digital_setpoint_in2':
            pid = self._get_pid('in2')
            status['digital_setpoint_array'] = self.current['in2']['digital_setpoint_array']
            status['setpoint_in_sequence'] = self.dig2phy_setpoint_in2(float(pid.setpoint_in_sequence))
            print(pid.setpoint_in_sequence)
        elif self.setpoint_source == 'digital_setpoint_in1':
            pid = self._get_pid('in1')
            status['digital_setpoint_array'] = self.current['in1']['digital_setpoint_array']
            status['setpoint_in_sequence'] = self.dig2phy_setpoint_in1(float(pid.setpoint_in_sequence))
            print(pid.setpoint_in_sequence)
        elif self.setpoint_source == 'analog_setpoint':
            pid = self._get_pid('in1')
        try:
            status['setpoint_source'] = self.setpoint_source
            # Current parameter values - check which attributes exist
            status['p'] = float(pid.p)
            status['i'] = float(pid.i)
            if self.setpoint_source == 'digital_setpoint_in2':
                status['setpoint'] = self.dig2phy_setpoint_in2(pid.setpoint)
            else:
                status['setpoint'] = self.dig2phy_setpoint_in1(pid.setpoint)
            status['ival'] = float(pid.ival)
            
            # Control settings
            status['input'] = str(pid.input)
            status['output_direct'] = str(pid.output_direct)
            status['pause_gains'] = str(pid.pause_gains)  # Keep as string, don't convert to int
            
            # Check paused status - use the actual paused attribute if available
            status['paused'] = bool(pid.paused)
            
            # Voltage limits
            status['min_voltage'] = float(pid.min_voltage)+OUT_ZERO
            status['max_voltage'] = float(pid.max_voltage)+OUT_ZERO

            status['differential_mode_enabled'] = bool(pid.differential_mode_enabled)

            status['setpoint_source'] = self.setpoint_source

            status['use_setpoint_sequence'] = bool(pid.use_setpoint_sequence)
            status['setpoint_index'] = int(pid.setpoint_index)
            status['sequence_wrap_flag'] = bool(pid.sequence_wrap_flag)

            print(f"[WORKER] Hardware status check completed")
            print(status)
            return status
            
        except Exception as e:
            print(f"[WORKER] Hardware status check failed: {e}")
            return {'error': str(e)}

    def get_error_point(self):
        """Return a single (time, error, ival) point for a specific PID."""
        import time
        import traceback
        if self.setpoint_source == 'digital_setpoint_in2':
            pid = self._get_pid('in2')
        else:
            pid = self._get_pid('in1')
        try:
            now = time.time()
            if self.setpoint_source == 'digital_setpoint_in1':
                val_in = self.p.rp.scope.voltage_in1
                if pid.use_setpoint_sequence:
                    error = val_in - pid.setpoint_in_sequence
                else:
                    error = val_in - pid.setpoint
            elif self.setpoint_source == 'digital_setpoint_in2':
                val_in = self.p.rp.scope.voltage_in2
                if pid.use_setpoint_sequence:
                    error = val_in - pid.setpoint_in_sequence
                else:
                    error = val_in - pid.setpoint
            else:  # analog_setpoint
                val_in = self.p.rp.scope.voltage_in1
                val_sp = self.p.rp.scope.voltage_in2
                error = val_in - val_sp
            print(pid.ival)
            print(f"[DEBUG] get_error_point: time={now}, error={error}, ival={pid.ival}")

            return {'time': now, 'error': error, 'ival': pid.ival}
        except Exception as e:
            error_msg = f"Error in get_error_point: {str(e)}\n{traceback.format_exc()}"
            print(f"[ERROR] {error_msg}")
            return {'ERROR': error_msg}
    
    def pause_pid(self):
        try:
            self.pids['in1'].paused = True
            self.pids['in2'].paused = True
            print("[DEBUG] PID controllers paused")
            return {'in1': self.pids['in1'].paused, 'in2': self.pids['in2'].paused}
        except Exception as e:
            print(f"[ERROR] Failed to pause PID controllers: {e}")
            return {"error": f"Failed to pause PID controllers: {e}"}

    def output_to_zero(self):
        try:
            self.pids['in1'].pause_gains = 'pi'
            self.pids['in2'].pause_gains = 'pi'
            self.pids['in1'].paused = True
            self.pids['in2'].paused = True
            self.pids['in1'].p = 0.0
            self.pids['in2'].p = 0.0
            self.pids['in1'].ival = -0.99
            self.pids['in2'].ival = -0.99
            print("[DEBUG] PID controllers output set to zero")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to set PID controllers output to zero: {e}")

    # because of the calibration issue, we need to manually calibrate the digital setpoints
    def phy2dig_setpoint_in1(self, physical_value):
        k1 = (HALF_IN1 - ZERO_IN1)/0.5
        b1 = ZERO_IN1
        return k1 * physical_value + b1

    def dig2phy_setpoint_in1(self, digital_value):
        k1 = (0.5 - 0.0) / (HALF_IN1 - ZERO_IN1)
        b1 = 0.0 - k1 * ZERO_IN1
        return k1 * digital_value + b1

    def phy2dig_setpoint_in2(self, physical_value):
        k2 = (HALF_IN2 - ZERO_IN2)/0.5
        b2 = ZERO_IN2
        return k2 * physical_value + b2

    def dig2phy_setpoint_in2(self, digital_value):
        k2 = (0.5 - 0.0) / (HALF_IN2 - ZERO_IN2)
        b2 = 0.0 - k2 * ZERO_IN2
        return k2 * digital_value + b2

        # ---------- Digital Setpoint Sequence Methods ----------
    def set_use_setpoint_sequence(self, enable):
        """Enable/disable setpoint sequence mode"""
        try:
            if self.setpoint_source == 'digital_setpoint_in2':
                self.pids['in2'].use_setpoint_sequence = bool(enable)
                return self.pids['in2'].use_setpoint_sequence
            elif self.setpoint_source == 'digital_setpoint_in1':
                self.pids['in1'].use_setpoint_sequence = bool(enable)
                return self.pids['in1'].use_setpoint_sequence
        except Exception as e:
            print(f"[WORKER] set_use_setpoint_sequence error: {e}")
            raise

    def set_setpoint_array(self, array):
        """Set setpoint array for sequence mode"""
        try:
            # Pad array to 16 elements with zeros if shorter
            if len(array) < 16:
                array = list(array) + [0.0] * (16 - len(array))
                print(f"[WORKER] Array padded to 16 elements with zeros")
            
            if self.setpoint_source == 'digital_setpoint_in2':
                digital_array = [self.phy2dig_setpoint_in2(val) for val in array]
                self.current['in2']['digital_setpoint_array'] = array
                self.pids['in2'].set_setpoint_array(digital_array)
            elif self.setpoint_source == 'digital_setpoint_in1':
                digital_array = [self.phy2dig_setpoint_in1(val) for val in array]
                self.current['in1']['digital_setpoint_array'] = array
                self.pids['in1'].set_setpoint_array(digital_array)
            return f"Setpoint array set: {array} -> {digital_array}"
        except Exception as e:
            print(f"[WORKER] set_setpoint_array error: {e}")
            raise

    def reset_sequence_index(self):
        """Reset sequence index to 0"""
        try:
            if self.setpoint_source == 'digital_setpoint_in2':
                self.pids['in2'].reset_sequence_index()
            elif self.setpoint_source == 'digital_setpoint_in1':
                self.pids['in1'].reset_sequence_index()
            return "Sequence index reset to 0"
        except Exception as e:
            print(f"[WORKER] reset_sequence_index error: {e}")
            raise

    def manually_change_setpoint(self):
        """Manually trigger setpoint change in sequence"""
        try:
            if self.setpoint_source == 'digital_setpoint_in2':
                self.pids['in2'].manually_change_setpoint()
            elif self.setpoint_source == 'digital_setpoint_in1':
                self.pids['in1'].manually_change_setpoint()
            return "Setpoint manually changed"
        except Exception as e:
            print(f"[WORKER] manually_change_setpoint error: {e}")
            raise



    def set_setpoint_index(self, index):
        """Set setpoint index (0-15)"""
        try:
            if self.setpoint_source == 'digital_setpoint_in2':
                self.pids['in2'].setpoint_index = int(index) & 0xF
                return self.pids['in2'].setpoint_index
            elif self.setpoint_source == 'digital_setpoint_in1':
                self.pids['in1'].setpoint_index = int(index) & 0xF
                return self.pids['in1'].setpoint_index
        except Exception as e:
            print(f"[WORKER] set_setpoint_index error: {e}")
            raise

    # ---------- BLACS required methods ----------
    def program_manual(self, values):
        return {}

    def transition_to_manual(self):
        try:
            sp1 = self.dig2phy_setpoint_in1(self.pids['in1'].setpoint)
            sp2 = self.dig2phy_setpoint_in2(self.pids['in2'].setpoint)
            return {'in1': float(sp1), 'in2': float(sp2)}
        except Exception as e:
            print(f"[WORKER] transition_to_manual error: {e}")
            return {'in1': 0.0}

    def transition_to_buffered(self, device_name, h5_file, initial_values, fresh):
        """Read simplified parameters from HDF5 and configure hardware"""
        print(f"[WORKER] transition_to_buffered called: device={device_name}, fresh={fresh}")
        print("0")
        
        try:
            import h5py
            
            with h5py.File(h5_file, 'r') as hdf5_file:
                device_group = hdf5_file[f'/devices/{device_name}']
                print("1")
                print(device_group)
                
                # Process each channel's parameters
                for channel in ['in1', 'in2']:
                    if channel in device_group:
                        channel_group = device_group[channel]
                        pid = self.pids[channel]
                        
                        if 'digital_setpoint_array' in channel_group:
                            array = list(channel_group['digital_setpoint_array'][:])
                            # Use worker's method to handle calibration
                            if channel == 'in1':
                                digital_array = [self.phy2dig_setpoint_in1(val) for val in array]
                                self.current['in1']['digital_setpoint_array'] = array
                                pid.set_setpoint_array(digital_array)
                                pid.reset_sequence_index()
                            else:  # in2
                                digital_array = [self.phy2dig_setpoint_in2(val) for val in array]
                                self.current['in2']['digital_setpoint_array'] = array  
                                pid.set_setpoint_array(digital_array)
                                pid.reset_sequence_index()
                            print(f"[WORKER] Set {channel}.digital_setpoint_array = {array}")
            
            print(f"[WORKER] transition_to_buffered completed successfully")
            return {}
            
        except Exception as e:
            print(f"[WORKER] transition_to_buffered failed: {e}")
            import traceback
            traceback.print_exc()
            return {}

    def abort_buffered(self):
        """Abort buffered mode - pause PIDs safely"""
        try:
            for channel in ['in1', 'in2']:
                pid = self.pids[channel]
                pid.pause_gains = 'pi'  # Pause both P and I
                pid.paused = True
                pid.ival = -0.99        # Reset integrator
            print("[WORKER] Buffered mode aborted - PIDs paused")
            return True
        except Exception as e:
            print(f"[WORKER] Error in abort_buffered: {e}")
            return False

    def abort_transition_to_buffered(self):
        """Abort transition to buffered mode"""
        try:
            for channel in ['in1', 'in2']:
                pid = self.pids[channel]
                pid.pause_gains = 'pi'  # Pause both P and I
                pid.paused = True
                pid.ival = -0.99        # Reset integrator
            print("[WORKER] Transition to buffered aborted - PIDs paused")
            return True
        except Exception as e:
            print(f"[WORKER] Error in abort_transition_to_buffered: {e}")
            return False

    def shutdown(self):
        """Shutdown worker - ensure safe state"""
        try:
            for channel in ['in1', 'in2']:
                pid = self.pids[channel]
                pid.pause_gains = 'pi'  # Pause both P and I
                pid.paused = True
                pid.ival = -0.99        # Reset integrator
            print("[WORKER] Worker shutdown - all PIDs safely paused")
        except Exception as e:
            print(f"[WORKER] Error during shutdown: {e}")
            pass