
#####################################################################
#                                                                   #
# Red Pitaya PID (pyrpl) BLACS Tab                                  #
#                                                                   #
# Based on examples from:                                            #
# - red_pitaya_pyrpl_asg_python3.7.5                                 #
# - Windfreak/RedPitayaPID                                           #
#                                                                   #
#####################################################################

print("Loading Red Pitaya PID BLACS Tab...")

import os
from pathlib import Path

from blacs.device_base_class import DeviceTab
from blacs.tab_base_classes import define_state, MODE_MANUAL, MODE_BUFFERED, MODE_TRANSITION_TO_MANUAL

from qtutils import UiLoader
from qtutils.qt.QtCore import *  # noqa: F401,F403
from qtutils.qt.QtGui import *   # noqa: F401,F403
from qtutils.qt.QtWidgets import QLabel, QComboBox, QPushButton, QMessageBox, QSizePolicy, QVBoxLayout  # noqa: F401,F403
from qtutils.qt.QtCore import QTimer
from qtutils.qt.QtWidgets import *  # noqa: F401,F403

import pyqtgraph as pg

# calibrate the output range
OUT_MAX = 2.031
OUT_MIN = 0.007
OUT_ZERO = (OUT_MAX + OUT_MIN) / 2


class red_pitaya_pyrpl_pid_tab(DeviceTab):
    """BLACS Tab for controlling Red Pitaya PID via pyrpl."""
    
    # Specify that this device has no output channels
    #device_worker_class = 'labscript_devices.red_pitaya_pyrpl_pid.blacs_workers.red_pitaya_pyrpl_pid_worker'
    device_worker_class = 'user_devices.Cesium.red_pitaya_pyrpl_pid.blacs_workers.red_pitaya_pyrpl_pid_worker'

    def initialise_GUI(self):
        """Build the GUI from .ui if available, otherwise create a simple one programmatically."""
        layout = self.get_tab_layout()
        ui_path = Path(__file__).parent / 'red_pitaya_pyrpl_pid.ui'

        self._has_loaded_ui = False
        if ui_path.exists():
            try:
                self.ui = UiLoader().load(str(ui_path))
                layout.addWidget(self.ui)
                expected_attrs = ['setpointEdit', 'pGainEdit', 'iGainEdit', 'dGainEdit']
                if all(hasattr(self.ui, attr) for attr in expected_attrs):
                    self._has_loaded_ui = True
                else:
                    self._has_loaded_ui = False
                    layout.removeWidget(self.ui)
                    self.ui.setParent(None)
                    self._build_fallback_ui(layout)
            except Exception:
                self._build_fallback_ui(layout)
        else:
            self._build_fallback_ui(layout)

        # Wire up signals if using fallback UI
        if not self._has_loaded_ui:
            self._setup_fallback_signal_connections()

    def _build_fallback_ui(self, layout):
        """Create a basic PID control UI programmatically."""
        scroll = QScrollArea()
        widget = QWidget()
        
        grid = QGridLayout(widget)
        grid.setSpacing(10)

        # Status
        status_group = QGroupBox('Status')
        status_layout = QGridLayout(status_group)
        self.status_label = QLabel('Not connected')
        self.status_label.setStyleSheet('color: orange; font-weight: bold;')
        status_layout.addWidget(self.status_label, 0, 0, 1, 2)
        self.write_to_config_button = QPushButton('Write to Config')
        status_layout.addWidget(self.write_to_config_button, 1, 0, 1, 1)
        self.pause_pid_button = QPushButton('Pause PID')
        status_layout.addWidget(self.pause_pid_button, 1, 1, 1, 1)
        self.output_to_zero_button = QPushButton('Output to Zero and Pause')
        status_layout.addWidget(self.output_to_zero_button, 1, 2, 1, 1)

        # setpoint_source
        setpoint_source_group = QGroupBox('Setpoint Source')
        setpoint_source_layout = QGridLayout(setpoint_source_group)
        self.setpoint_source_combo = QComboBox()
        self.setpoint_source_combo.addItems(['analog_setpoint', 'digital_setpoint_in1', 'digital_setpoint_in2'])
        self.setpoint_source_combo.setCurrentText('digital_setpoint_in1')
        setpoint_source_layout.addWidget(self.setpoint_source_combo)
        status_layout.addWidget(setpoint_source_group, 2, 0, 1, 1)

        # Setpoint Sequence Group
        sequence_group = QGroupBox('Setpoint Sequence')
        sequence_layout = QGridLayout(sequence_group)
        
        # Use sequence checkbox
        sequence_layout.addWidget(QLabel('Use Sequence:'), 0, 0)
        self.use_sequence_checkbox = QCheckBox()
        sequence_layout.addWidget(self.use_sequence_checkbox, 0, 1)
        
        # Setpoint array input
        self.array_label = QLabel('Array (Python expr):')
        sequence_layout.addWidget(self.array_label, 1, 0)
        self.setpoint_array_edit = QLineEdit('np.zeros(16)')
        self.setpoint_array_edit.setToolTip('Enter Python expression like: np.zeros(16), np.linspace(-0.5,0.5,16), [0.1]*16, etc.')
        sequence_layout.addWidget(self.setpoint_array_edit, 1, 1, 1, 2)
        
        # Current sequence info
        self.index_label = QLabel('Index (0-15):')
        sequence_layout.addWidget(self.index_label, 2, 0)
        self.setpoint_index_edit = QLineEdit('0')
        self.setpoint_index_edit.setMaxLength(2)
        self.setpoint_index_edit.setToolTip('Current sequence index (press Enter to change)')
        sequence_layout.addWidget(self.setpoint_index_edit, 2, 1)
        
        self.current_value_label = QLabel('Current Setpoint:')
        sequence_layout.addWidget(self.current_value_label, 3, 0)
        self.sequence_value_label = QLabel('0.0')
        sequence_layout.addWidget(self.sequence_value_label, 3, 1)
        
        self.last_setpoint_label = QLabel('Last setpoint:')
        sequence_layout.addWidget(self.last_setpoint_label, 4, 0)
        self.wrap_flag_label = QLabel('Not Triggered')
        sequence_layout.addWidget(self.wrap_flag_label, 4, 1)
        
        # Control buttons
        button_layout = QHBoxLayout()
        self.reset_index_button = QPushButton('Reset Index')
        self.manual_step_button = QPushButton('Manual Step')
        button_layout.addWidget(self.reset_index_button)
        button_layout.addWidget(self.manual_step_button)
        sequence_layout.addLayout(button_layout, 5, 0, 1, 3)

        # Initially disable all sequence controls (will be enabled when Use Sequence is checked)
        self.array_label.setEnabled(False)
        self.setpoint_array_edit.setEnabled(False)
        self.index_label.setEnabled(False)
        self.setpoint_index_edit.setEnabled(False)
        self.current_value_label.setEnabled(False)
        self.sequence_value_label.setEnabled(False)
        self.last_setpoint_label.setEnabled(False)
        self.wrap_flag_label.setEnabled(False)
        self.reset_index_button.setEnabled(False)
        self.manual_step_button.setEnabled(False)

        # Parameters
        params_group = QGroupBox('PID Parameters')
        params = QGridLayout(params_group)
        # Setpoint
        params.addWidget(QLabel('Setpoint (V):'), 0, 0)
        self.setpoint_edit = QLineEdit('0.0')
        params.addWidget(self.setpoint_edit, 0, 1)
        # Gains
        params.addWidget(QLabel('P:'), 1, 0)
        self.p_edit = QLineEdit('0')
        params.addWidget(self.p_edit, 1, 1)
        params.addWidget(QLabel('I:'), 2, 0)
        self.i_edit = QLineEdit('0')
        params.addWidget(self.i_edit, 2, 1)
        params.addWidget(QLabel('Min V:'), 3, 0)
        self.min_edit = QLineEdit(str(OUT_MIN))
        params.addWidget(self.min_edit, 3, 1)
        params.addWidget(QLabel('Max V:'), 4, 0)
        self.max_edit = QLineEdit(str(OUT_MAX))
        params.addWidget(self.max_edit, 4, 1)
        params.addWidget(QLabel('Ival:'), 5, 0)
        self.ival_edit = QLineEdit('0.0')
        params.addWidget(self.ival_edit, 5, 1)
        # Pause Gains Combo
        params.addWidget(QLabel('Pause Gains:'), 6, 0)
        self.pause_gains_combo = QComboBox()
        self.pause_gains_combo.addItems(['pi', 'p', 'i','off'])
        params.addWidget(self.pause_gains_combo, 6, 1)

        params.addWidget(QLabel('Input:'), 7, 0)
        self.input_combo = QComboBox()
        self.input_combo.addItems(['in1'])
        params.addWidget(self.input_combo, 7, 1)
        params.addWidget(QLabel('Direct Out:'), 8, 0)
        self.output_combo = QComboBox()
        self.output_combo.addItems(['out1', 'off'])
        params.addWidget(self.output_combo, 8, 1)

        self.btn_enable = QPushButton('Enable PID')
        self.btn_enable.setStyleSheet('background: green; color: white;')
        self.btn_disable = QPushButton('Disable PID')
        self.btn_disable.setStyleSheet('background: red; color: white;')
        self.btn_reset = QPushButton('Reset PID (p=0,i=0,ival=0)')
        self.btn_reset.setStyleSheet('border:2px solid #000000;')
        self.btn_refresh = QPushButton('Refresh and Read')
        self.btn_refresh.setStyleSheet('border:2px solid #000000;')
        params.addWidget(self.btn_enable, 9, 0)
        params.addWidget(self.btn_disable, 10, 0)
        params.addWidget(self.btn_reset, 9, 1)
        params.addWidget(self.btn_refresh, 10, 1)

        """Create a basic PID control UI programmatically."""

        self.plot_group = QGroupBox('Error Plot')
        self.plot_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.plot_group.setMinimumHeight(450)
        
        plot_layout = QVBoxLayout(self.plot_group)
        
        self.plot_widget = pg.PlotWidget(self.plot_group, title="PID Error and Ival")
        self.plot_widget.setLabel('bottom', 'Relative Time (s)')
        self.plot_widget.setLabel('left', 'Error (Input-Setpoint)')
        self.plot_widget.showGrid(x=True, y=True)

        self.right_axis = pg.ViewBox()
        self.plot_widget.showAxis('right')
        self.plot_widget.scene().addItem(self.right_axis)
        self.plot_widget.getAxis('right').linkToView(self.right_axis)
        self.right_axis.setXLink(self.plot_widget)

        self.error_line = self.plot_widget.plot(pen=pg.mkPen('y', width=2), name='Error=Input-Setpoint')

        self.ival_line = pg.PlotDataItem(pen=pg.mkPen('r', width=2), name='Ival')
        self.right_axis.addItem(self.ival_line)
        self.plot_widget.getAxis('right').setLabel('Ival')

        legend = pg.LegendItem(offset=(70, 30))
        legend.setParentItem(self.plot_widget.graphicsItem())
        legend.addItem(self.error_line, name='Error=Input-Setpoint')
        legend.addItem(self.ival_line, name='Ival')

        def updateViews():
            self.right_axis.setGeometry(self.plot_widget.getViewBox().sceneBoundingRect())
            self.right_axis.linkedViewChanged(self.plot_widget.getViewBox(), self.right_axis.XAxis)
        self.plot_widget.getViewBox().sigResized.connect(updateViews)

        # Set initial range and disable auto-scaling to fix the x-axis
        self.plot_widget.setXRange(0, 5, padding=0)
        self.plot_widget.setLimits(xMin=0, xMax=5)
        self.plot_widget.setYRange(-1, 1)

        plot_layout.addWidget(self.plot_widget)
        self.btn_rolling_plot = QPushButton('Start Rolling Plot')
        self.btn_rolling_plot.setCheckable(True)
        plot_layout.addWidget(self.btn_rolling_plot)
        self._auto_plot_timer = QTimer()
        self._auto_plot_timer.setInterval(100)  # 10Hz update rate

        # Layout
        grid.addWidget(status_group, 0, 0, 1, 3)
        grid.addWidget(setpoint_source_group, 1, 0, 1, 1)
        grid.addWidget(sequence_group, 1, 1, 1, 1)
        grid.addWidget(params_group, 2, 0)
        grid.addWidget(self.plot_group, 2, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 2)

        scroll.setWidget(widget)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)

    def _setup_fallback_signal_connections(self):
    # Parameters - use Windfreak style: direct connection to @define_state methods
        self.setpoint_edit.returnPressed.connect(self._set_setpoint)
        self.p_edit.returnPressed.connect(self._set_p)
        self.i_edit.returnPressed.connect(self._set_i)
        self.min_edit.returnPressed.connect(self._apply_limits)
        self.max_edit.returnPressed.connect(self._apply_limits)
        self.ival_edit.returnPressed.connect(self._set_ival)
        self.btn_refresh.clicked.connect(self._check_hardware_status)
        self.input_combo.currentTextChanged.connect(self._set_input)
        self.output_combo.currentTextChanged.connect(lambda text: self._set_output_direct(text) if text else None)
        self.btn_enable.clicked.connect(self._enable_pid)
        self.btn_disable.clicked.connect(self._disable_pid) 
        self.btn_reset.clicked.connect(self._reset_pid)
        self.pause_gains_combo.currentTextChanged.connect(self._set_pause_gains)
        self.setpoint_source_combo.currentTextChanged.connect(self._set_setpoint_source)
        self.btn_rolling_plot.toggled.connect(self._toggle_rolling_plot)
        self.write_to_config_button.clicked.connect(self._write_to_config)
        self.pause_pid_button.clicked.connect(self._pause_pid)
        self.output_to_zero_button.clicked.connect(self._output_to_zero)

        # Sequence control connections
        self.use_sequence_checkbox.toggled.connect(self._set_use_sequence)
        self.setpoint_array_edit.returnPressed.connect(self._set_setpoint_array)
        self.reset_index_button.clicked.connect(self._reset_sequence_index)
        self.manual_step_button.clicked.connect(self._manually_change_setpoint)
        self.setpoint_index_edit.returnPressed.connect(self._set_setpoint_index)


    # === WINDFREAK STYLE INDIVIDUAL PARAMETER METHODS ===

    @define_state(MODE_MANUAL, True)
    def _set_p(self, *args):
        """Set P parameter - Windfreak style"""
        try:
            text = self.p_edit.text()
            val = float(text)
            result = yield(self.queue_work(self.primary_worker, 'set_p', val))

            # Update UI with actual hardware value
            if isinstance(result, (int, float)):
                self.p_edit.setText(f"{result:.6f}")

            self._update_status(f"P = {result}")
        except Exception as e:
            print(f"[TABS] _set_p error: {e}")
            self._update_status(f"Error: {e}")
        return

    @define_state(MODE_MANUAL, True)
    def _set_i(self, *args):
        """Set I parameter - Windfreak style"""
        try:
            text = self.i_edit.text()
            val = float(text)
            print(f"[DEBUG] _set_i called with value: {val}")

            result = yield(self.queue_work(self.primary_worker, 'set_i', val))
            print(f"[DEBUG] _set_i result: {result}")

            # Update UI with actual hardware value
            if isinstance(result, (int, float)):
                self.i_edit.setText(f"{result:.6f}")
                
            self._update_status(f"I = {result}")
        except Exception as e:
            print(f"[TABS] _set_i error: {e}")
            self._update_status(f"Error: {e}")
        return

    @define_state(MODE_MANUAL, True)
    def _set_ival(self, *args):
        """Set ival parameter - Windfreak style"""
        try:
            text = self.ival_edit.text()
            val = float(text)
            print(f"[DEBUG] _set_ival called with value: {val}")
            
            result = yield(self.queue_work(self.primary_worker, 'set_ival', val))
            print(f"[DEBUG] _set_ival result: {result}")
            
            # Update UI with actual hardware value
            if isinstance(result, (int, float)):
                self.ival_edit.setText(f"{result:.6f}")
                
            self._update_status(f"ival = {result}")
        except Exception as e:
            print(f"[TABS] _set_ival error: {e}")
            self._update_status(f"Error: {e}")
        return

    @define_state(MODE_MANUAL, True)
    def _set_setpoint(self, *args):
        """Set Setpoint parameter - Windfreak style"""
        try:
            text = self.setpoint_edit.text()
            val = float(text)
            print(f"[DEBUG] _set_setpoint called with value: {val}")
            
            result = yield(self.queue_work(self.primary_worker, 'set_setpoint', val))
            print(f"[DEBUG] _set_setpoint result: {result}")
            
            # Update UI with actual hardware value
            if isinstance(result, (int, float)):
                self.setpoint_edit.setText(f"{result:.6f}")
                
            self._update_status(f"Setpoint = {result}")
        except Exception as e:
            print(f"[TABS] _set_setpoint error: {e}")
            self._update_status(f"Error: {e}")
        return

    @define_state(MODE_MANUAL, True)
    def _check_hardware_status(self, *args):
        """Check detailed hardware status and update UI values - Windfreak style"""
        try:
            print(f"[DEBUG] _check_hardware_status called")
            
            result = yield(self.queue_work(self.primary_worker, 'check_hardware_status'))
            print(f"[TABS] Hardware status result: {result}")
                
            # Show key status in UI
            if isinstance(result, dict) and 'error' not in result:
                # Initialize paused variable at the start
                paused = result.get('paused', False)
                
                # Update UI input fields with current hardware values
                try:
                    self.p_edit.setText(f"{result.get('p', 0.0):.6f}")
                    self.i_edit.setText(f"{result.get('i', 0.0):.6f}")
                    self.ival_edit.setText(f"{result.get('ival', 0.0):.6f}")
                    self.setpoint_edit.setText(f"{result.get('setpoint', 0.0):.6f}")
                    
                    # Update other fields too
                    self.min_edit.setText(f"{result.get('min_voltage', OUT_MIN):.6f}")
                    self.max_edit.setText(f"{result.get('max_voltage', OUT_MAX):.6f}")

                    # Update combo boxes
                    self.pause_gains_combo.blockSignals(True)
                    self.pause_gains_combo.setCurrentText(result['pause_gains'])
                    self.pause_gains_combo.blockSignals(False)
                    
                    self.setpoint_source_combo.blockSignals(True)
                    self.setpoint_source_combo.setCurrentText(result['setpoint_source'])
                    self.setpoint_source_combo.blockSignals(False)
                    print(f"[DEBUG] Setpoint source: {result['setpoint_source']}")

                    # Convert digital_setpoint_array to string for display
                    array_data = result.get('digital_setpoint_array', [])
                    array_str = str(array_data)
                    
                    self.setpoint_array_edit.blockSignals(True)
                    self.setpoint_array_edit.setText(array_str)
                    self.setpoint_array_edit.blockSignals(False)

                    self.setpoint_index_edit.blockSignals(True)
                    self.setpoint_index_edit.setText(f"{result['setpoint_index']}")
                    self.setpoint_index_edit.blockSignals(False)

                    # Update sequence value display (only the value label, not the description label)
                    self.sequence_value_label.setText(f"{result.get('setpoint_in_sequence', 0.0):.6f}")

                    if result['setpoint_source'] == 'analog_setpoint':
                        self.setpoint_edit.setEnabled(False)
                        self.input_combo.setEnabled(False)
                        self.output_combo.setEnabled(False)
                        self._set_use_sequence(False)
                        self._reset_sequence_index()
                    elif result['setpoint_source'] == 'digital_setpoint_in1':
                        self.setpoint_edit.setEnabled(True)
                        self.input_combo.setEnabled(True)
                        self.output_combo.setEnabled(True)
                        if result['use_setpoint_sequence']:
                            self._set_use_sequence(True)
                        else:
                            self._set_use_sequence(False)
                        self.input_combo.blockSignals(True)
                        self.input_combo.clear()
                        self.input_combo.addItem('in1')
                        self.input_combo.setCurrentText(result['input'])
                        self.input_combo.blockSignals(False)
                        self.output_combo.blockSignals(True)
                        self.output_combo.clear()
                        self.output_combo.addItems(['out1','off'])
                        self.output_combo.setCurrentText(result['output_direct'])
                        self.output_combo.blockSignals(False)
                    elif result['setpoint_source'] == 'digital_setpoint_in2':
                        self.setpoint_edit.setEnabled(True)
                        self.input_combo.setEnabled(True)
                        self.output_combo.setEnabled(True)
                        if result['use_setpoint_sequence']:
                            self._set_use_sequence(True)
                        else:
                            self._set_use_sequence(False)
                        self.input_combo.blockSignals(True)
                        self.input_combo.clear()
                        self.input_combo.addItem('in2')
                        self.input_combo.setCurrentText(result['input'])
                        self.input_combo.blockSignals(False)
                        self.output_combo.blockSignals(True)
                        self.output_combo.clear()
                        self.output_combo.addItems(['out2', 'off'])
                        self.output_combo.setCurrentText(result['output_direct'])
                        self.output_combo.blockSignals(False)

                    print(f"[DEBUG] Updated UI fields: p={result.get('p')}, i={result.get('i')}, ival={result.get('ival')}, setpoint={result.get('setpoint')}, min_voltage={result.get('min_voltage')}, max_voltage={result.get('max_voltage')}, input={result.get('input')}, output={result.get('output_direct')}, pause_gains={result.get('pause_gains')}, paused={paused}")
                    print(f"[DEBUG] Updated UI fields: {result}")

                except Exception as ui_error:
                    print(f"[TABS] Error updating UI fields: {ui_error}")

                wrap_flag = result['sequence_wrap_flag']
                # Set wrap flag display with human-readable text and colors
                if wrap_flag:
                    self.wrap_flag_label.setText("Triggered")
                    self.wrap_flag_label.setStyleSheet('color: #00FF00; font-weight: bold; background-color: rgba(0, 255, 0, 30); padding: 2px; border-radius: 3px;')
                else:
                    self.wrap_flag_label.setText("Not Triggered")
                    self.wrap_flag_label.setStyleSheet('color: #666666; font-weight: normal;')
                            

                self._update_status(f"Updated UI fields, paused={paused}")
            else:
                self._update_status(f"Hardware status error: {result}")
                
        except Exception as e:
            print(f"[TABS] _check_hardware_status error: {e}")
            self._update_status(f"Status check error: {e}")
        return

    @define_state(MODE_MANUAL, True)
    def _enable_pid(self, *args):
        """Enable PID controller - Windfreak style"""
        try:
            print(f"[DEBUG] _enable_pid called")
            
            result = yield(self.queue_work(self.primary_worker, 'enable_pid'))
            print(f"[DEBUG] Enable PID result: {result}")
                
            if isinstance(result, bool) and result:
                self._update_status("PID Enabled")
            else:
                self._update_status(f"PID enable failed: {result}")
                
        except Exception as e:
            print(f"[TABS] Enable PID error: {e}")
            self._update_status(f"Enable error: {e}")

    @define_state(MODE_MANUAL, True) 
    def _disable_pid(self, *args):
        """Disable PID controller - Windfreak style"""
        try:
            print(f"[DEBUG] _disable_pid called")
            
            result = yield(self.queue_work(self.primary_worker, 'disable_pid'))
            print(f"[DEBUG] Disable PID result: {result}")
                
            if isinstance(result, bool) and result:
                self._update_status("PID Disabled")
            else:
                self._update_status(f"PID disable failed: {result}")
                
        except Exception as e:
            print(f"[TABS] Disable PID error: {e}")
            self._update_status(f"Disable error: {e}")

    @define_state(MODE_MANUAL, True)
    def _reset_pid(self, *args):
        """Reset PID controller - sets p, i, ival to 0"""
        try:
            print(f"[DEBUG] _reset_pid called - will set p=0, i=0, ival=0")
            
            result = yield(self.queue_work(self.primary_worker, 'reset_pid'))
            print(f"[DEBUG] Reset PID result: {result}")
                
            self._update_status("PID Reset (p=0, i=0, ival=0)")
            self._check_hardware_status()

        except Exception as e:
            print(f"[TABS] Reset PID error: {e}")
            self._update_status(f"Reset error: {e}")

    @define_state(MODE_MANUAL, True)
    def _set_output_direct(self, output_value, *args):
        """Set output direct - Windfreak style"""
        try:
            print(f"[DEBUG] _set_output_direct called with: {output_value}")
            
            result = yield(self.queue_work(self.primary_worker, 'set_output_direct', output_value))
            print(f"[DEBUG] Set output direct result: {result}")
            
            # Update UI with actual hardware value
            if isinstance(result, str):
                self.output_combo.setCurrentText(result)
                
            self._update_status(f"Output set to: {result} (UI Updated)")
                
        except Exception as e:
            print(f"[TABS] Set output direct error: {e}")
            self._update_status(f"Output setting error: {e}")

    @define_state(MODE_MANUAL, True)
    def _set_input(self, input_value, *args):
        """Set input - Windfreak style"""
        try:
            # if not input_value:  # empty string
            #     print("[DEBUG] _set_input ignored empty value")
            #     return
            # print(f"[DEBUG] _set_input called with: {input_value}")
            
            result = yield(self.queue_work(self.primary_worker, 'set_input', input_value))
            print(f"[DEBUG] Set input result: {result}")
            
            # Update UI with actual hardware value
            if isinstance(result, str):
                self.input_combo.setCurrentText(result)
            
            self._update_status(f"Input set to: {result} (UI Updated)")
                
        except Exception as e:
            print(f"[TABS] Set input error: {e}")
            self._update_status(f"Input setting error: {e}")

    @define_state(MODE_MANUAL, True)
    def _apply_limits(self, *args):
        """Apply voltage limits - Windfreak style"""
        try:
            print(f"[DEBUG] _apply_limits called")
            
            # Read min and max voltage from UI, because we remove the resistor, so we need 1.02V offset
            mn = float(self.min_edit.text())-OUT_ZERO
            mx = float(self.max_edit.text())-OUT_ZERO

            if mn >= mx:
                self._update_status('Error: Min voltage must be less than max voltage')
                return
            
            print(f"[DEBUG] Setting voltage limits: min={mn}, max={mx}")
            
            # Set min voltage
            result_min = yield(self.queue_work(self.primary_worker, 'set_min_voltage', mn))
            
            # Set max voltage
            result_max = yield(self.queue_work(self.primary_worker, 'set_max_voltage', mx))

            result_min_ui = result_min + OUT_ZERO
            result_max_ui = result_max + OUT_ZERO
            # Update UI with actual hardware values
            if isinstance(result_min, (int, float)):
                self.min_edit.setText(f"{result_min_ui:.6f}")

            if isinstance(result_max, (int, float)):
                self.max_edit.setText(f"{result_max_ui:.6f}")

            self._update_status(f'Limits: [{result_min_ui}, {result_max_ui}] V (UI Updated)')

        except ValueError:
            print(f"[TABS] _apply_limits ValueError")
            self._update_status('Error: Voltage limits need numeric values')
        except Exception as e:
            print(f"[TABS] _apply_limits error: {e}")
            self._update_status(f'Limits setting error: {e}')

    def _update_status(self, msg: str):
        if hasattr(self, 'status_label'):
            self.status_label.setText(msg)
            self.status_label.setStyleSheet('color: blue; font-weight: bold;')

    def initialise_workers(self):
        """Launch the worker process and pass connection info from the connection table."""
        connection_table = self.settings['connection_table']
        device = connection_table.find_by_name(self.device_name)
        ip_addr = device.properties.get('ip_addr')
        # Always use pid1 by default, do not pass pid_module
        self.create_worker(
            'rp_pid_main_worker',
            #'labscript_devices.red_pitaya_pyrpl_pid.blacs_workers.red_pitaya_pyrpl_pid_worker',
            'user_devices.Cesium.red_pitaya_pyrpl_pid.blacs_workers.red_pitaya_pyrpl_pid_worker',
            {'ip_addr': ip_addr}
        )
        self.primary_worker = 'rp_pid_main_worker'


    @define_state(MODE_MANUAL, True)
    def _set_pause_gains(self, *args):
        """Set pause_gains parameter from combo box"""
        try:
            value = self.pause_gains_combo.currentText()
            print(f"[DEBUG] _set_pause_gains called with value: {value}")
            result = yield(self.queue_work(self.primary_worker, 'set_pause_gains', value))
            print(f"[DEBUG] _set_pause_gains result: {result}")
            self._update_status(f"pause_gains = {result}")
        except Exception as e:
            print(f"[TABS] _set_pause_gains error: {e}")
            self._update_status(f"Error: {e}")
        return

    @define_state(MODE_MANUAL, True)
    def _set_setpoint_source(self, *args):#
        try:
            value = self.setpoint_source_combo.currentText()
            result = yield(self.queue_work(self.primary_worker, 'set_setpoint_source', value))
            print(f"[DEBUG] _set_setpoint_source result: {result}")
            # Disable setpoint, input, output and sequence controls if analog_setpoint
            if value == 'analog_setpoint':
                self.setpoint_edit.setEnabled(False)
                self.input_combo.setEnabled(False)
                self.output_combo.setEnabled(False) 
            elif value == 'digital_setpoint_in1':
                self.setpoint_edit.setEnabled(True)
                self.input_combo.setEnabled(True)
                self.output_combo.setEnabled(True)
                self.input_combo.blockSignals(True)
                self.input_combo.clear()
                self.input_combo.addItem('in1')
                self.input_combo.blockSignals(False)
                self.input_combo.setCurrentText('in1')
                self.output_combo.blockSignals(True)
                self.output_combo.clear()
                self.output_combo.addItems(['out1','off'])
                self.output_combo.blockSignals(False)
                self.output_combo.setCurrentText('out1')
            elif value == 'digital_setpoint_in2':
                self.setpoint_edit.setEnabled(True)
                self.input_combo.setEnabled(True)
                self.output_combo.setEnabled(True)
                self.input_combo.blockSignals(True)
                self.input_combo.clear()
                self.input_combo.addItem('in2')
                self.input_combo.blockSignals(False)
                self.input_combo.setCurrentText('in2')
                self.output_combo.blockSignals(True)
                self.output_combo.clear()
                self.output_combo.addItems(['out2', 'off'])
                self.output_combo.blockSignals(False)
                self.output_combo.setCurrentText('out2')
            self._update_status(f"setpoint_source = {result}")
            self._check_hardware_status()
        except Exception as e:
            print(f"[TABS] _set_setpoint_source error: {e}")
            self._update_status(f"Error: {e}")
        return

    def _start_rolling_plot(self):
        try:
            self._auto_plot_timer.timeout.disconnect()
        except TypeError:
            pass
        
        self._rolling_times = []
        self._rolling_errors = []
        self._rolling_ivals = []
        
        self.error_line.setData([], [])
        self.ival_line.setData([], [])
        
        self.plot_widget.setRange(xRange=[-5, 0], yRange=[-1, 1])
        
        self._auto_plot_timer.timeout.connect(self._update_rolling_plot)
        self._auto_plot_timer.start()

    @define_state(MODE_MANUAL, True)
    def _update_rolling_plot(self, *args):
        """Update rolling plot"""
        try:
            # result is a dictionary with keys 'time', 'error', 'ival'
            result = yield self.queue_work(self.primary_worker, 'get_error_point')
            
            if 'ERROR' in result:
                print(f"[ERROR] Rolling plot error: {result['ERROR']}")
                self._update_status(f": Rolling plot error: {result['ERROR'][:100]}...")
                return
            
            if not all(key in result for key in ['time', 'error', 'ival']):
                error_msg = f"Invalid data format: {list(result.keys())}"
                print(f"[ERROR] {error_msg}")
                self._update_status(f"Invalid data format: {error_msg}")
                return
            
            if not isinstance(result['time'], (int, float)) or not isinstance(result['error'], (int, float)) or not isinstance(result['ival'], (int, float)):
                error_msg = f"Invalid data types: time={type(result['time'])}, error={type(result['error'])}, ival={type(result['ival'])}"
                print(f"[ERROR] {error_msg}")
                self._update_status(f"Invalid data types: {error_msg}")
                return
            
            self._rolling_times.append(result['time'])
            self._rolling_errors.append(result['error'])
            self._rolling_ivals.append(result['ival'])

            # keep 5 seconds window
            tmax = self._rolling_times[-1]
            while self._rolling_times and tmax - self._rolling_times[0] > 5.0:
                self._rolling_times.pop(0)
                self._rolling_errors.pop(0)
                self._rolling_ivals.pop(0)
            
            tmin = self._rolling_times[0]
            relative_times = [t - tmin for t in self._rolling_times]

            self.error_line.setData(relative_times, self._rolling_errors)
            self.ival_line.setData(relative_times, self._rolling_ivals)
            self.plot_widget.enableAutoRange(axis='y', enable=True)
        
        except Exception as e:
            import traceback
            error_msg = f"Error in _update_rolling_plot: {str(e)}\n{traceback.format_exc()}"
            print(f"[CRITICAL] {error_msg}")
            self._update_status(f"Critical error: {error_msg[:100]}...")

    @define_state(MODE_MANUAL, True)
    def _toggle_rolling_plot(self, checked):
        if checked:
            self._start_rolling_plot()
            self.btn_rolling_plot.setText('Stop Rolling Plot')
        else:
            self._auto_plot_timer.stop()
            self.btn_rolling_plot.setText('Start Rolling Plot')
    
    @define_state(MODE_MANUAL, True)
    def _write_to_config(self, *args):
        yield self.queue_work(self.primary_worker, 'write_to_config')

    @define_state(MODE_MANUAL, True)
    def _pause_pid(self, *args):
        """pause PID"""
        try:
            print("[DEBUG] _pause_pid called")
            result = yield(self.queue_work(self.primary_worker, 'pause_pid'))
            print(f"[DEBUG] Pause PID result: {result}")
            if isinstance(result, dict):
                if 'error' in result:
                    self._update_status(f"PID pause failed: {result['error']}")
                else:
                    msg = []
                    for k in ('in1', 'in2'):
                        if k in result:
                            status = "paused" if result[k] else "not paused"
                            msg.append(f"{k}: {status}")
                    self._update_status("; ".join(msg))
            else:
                self._update_status(f"PID pause result: {result}")
        except Exception as e:
            print(f"[TABS] Pause PID error: {e}")
            self._update_status(f"Pause error: {e}")
        return

    @define_state(MODE_MANUAL, True)
    def _output_to_zero(self, *args):
        """Set the output to zero."""
        try:
            result = yield self.queue_work(self.primary_worker, 'output_to_zero')
            self._check_hardware_status()
            if result is not None:
                self._update_status(f"Output set to zero and paused: {result}")
        except Exception as e:
            print(f"[TABS] Output to zero error: {e}")
            self._update_status(f"Output to zero error: {e}")

    # === SETPOINT SEQUENCE METHODS ===

    @define_state(MODE_MANUAL, True)
    def _set_use_sequence(self, checked, *args):
        """Enable/disable setpoint sequence mode"""
        try:
            result = yield(self.queue_work(self.primary_worker, 'set_use_setpoint_sequence', checked))
            self._update_status(f"Use sequence: {result}")
            
            # Ensure checkbox reflects the actual state - use blockSignals to prevent recursion
            self.use_sequence_checkbox.blockSignals(True)
            self.use_sequence_checkbox.setChecked(bool(checked))
            self.use_sequence_checkbox.blockSignals(False)
            
            # Enable/disable sequence controls based on state
            self.array_label.setEnabled(checked)
            self.setpoint_array_edit.setEnabled(checked)
            self.index_label.setEnabled(checked)
            self.setpoint_index_edit.setEnabled(checked)
            self.current_value_label.setEnabled(checked)
            self.sequence_value_label.setEnabled(checked)
            self.last_setpoint_label.setEnabled(checked)
            self.wrap_flag_label.setEnabled(checked)
            self.reset_index_button.setEnabled(checked)
            self.manual_step_button.setEnabled(checked)
        except Exception as e:
            print(f"[TABS] _set_use_sequence error: {e}")
            self._update_status(f"Error: {e}")

    @define_state(MODE_MANUAL, True)
    def _set_setpoint_array(self, *args):
        """Set setpoint array from Python expression"""
        try:
            text = self.setpoint_array_edit.text().strip()
            
            if not text:
                self._update_status("Error: Empty expression")
                return
            
            # Safe evaluation of Python expressions
            import numpy as np
            import math
            
            # Create safe namespace for eval
            safe_dict = {
                "np": np,
                "numpy": np,
                "math": math,
                "zeros": np.zeros,
                "ones": np.ones,
                "linspace": np.linspace,
                "arange": np.arange,
                "array": np.array,
                "__builtins__": {}  # Remove builtins for security
            }
            
            try:
                # Evaluate the expression
                result_array = eval(text, safe_dict)
                
                # Convert to list if it's a numpy array
                if hasattr(result_array, 'tolist'):
                    array = result_array.tolist()
                elif isinstance(result_array, (list, tuple)):
                    array = list(result_array)
                else:
                    # Single value, create array
                    array = [float(result_array)]
                    
            except Exception as eval_error:
                self._update_status(f"Error evaluating expression: {eval_error}")
                return
                
            if not array:
                self._update_status("Error: Expression resulted in empty array")
                return
                
            if len(array) > 16:
                self._update_status(f"Error: Array too long ({len(array)} elements, max 16)")
                return
                
            # Ensure all elements are numbers
            try:
                array = [float(val) for val in array]
            except (ValueError, TypeError):
                self._update_status("Error: Array must contain only numbers")
                return
                
            result = yield(self.queue_work(self.primary_worker, 'set_setpoint_array', array))
            self._update_status(f"Array set ({len(array)} elements)")
            
        except Exception as e:
            print(f"[TABS] _set_setpoint_array error: {e}")
            self._update_status(f"Error: {e}")

    @define_state(MODE_MANUAL, True)
    def _reset_sequence_index(self, *args):
        """Reset sequence index to 0"""
        try:
            result = yield(self.queue_work(self.primary_worker, 'reset_sequence_index'))
            self._update_status(f"Index reset: {result}")
            
            # Reset trigger flag display to gray (Not Triggered)
            self.wrap_flag_label.setText("Not Triggered")
            self.wrap_flag_label.setStyleSheet('color: #666666; font-weight: normal;')
            
        except Exception as e:
            print(f"[TABS] _reset_sequence_index error: {e}")
            self._update_status(f"Error: {e}")

    @define_state(MODE_MANUAL, True)
    def _manually_change_setpoint(self, *args):
        """Manually trigger setpoint change in sequence"""
        try:
            result = yield(self.queue_work(self.primary_worker, 'manually_change_setpoint'))
            self._update_status(f"Manual step: {result}")
        except Exception as e:
            print(f"[TABS] _manually_change_setpoint error: {e}")
            self._update_status(f"Error: {e}")

    @define_state(MODE_MANUAL, True)
    def _set_setpoint_index(self, *args):
        """Set setpoint index directly"""
        try:
            text = self.setpoint_index_edit.text()
            index = int(text)
            
            if index < 0 or index > 15:
                self._update_status("Error: Index must be 0-15")
                return
                
            result = yield(self.queue_work(self.primary_worker, 'set_setpoint_index', index))
            self._update_status(f"Index set to: {result}")
        except ValueError:
            self._update_status("Error: Invalid index (use integer 0-15)")
        except Exception as e:
            print(f"[TABS] _set_setpoint_index error: {e}")
            self._update_status(f"Error: {e}")