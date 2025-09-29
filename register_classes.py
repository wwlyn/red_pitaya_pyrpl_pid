from labscript_devices import register_classes

# Use a unique name to avoid clashing with any built-in device of the same name
register_classes(
    'red_pitaya_pyrpl_pid',
    BLACS_tab='Cesium.userlib.red_pitaya_pyrpl_pid.blacs_tabs.red_pitaya_pyrpl_pid_tab',
    runviewer_parser=None,
)
