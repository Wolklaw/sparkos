"""Shared by the tests: a fake /sys/class/hwmon tree. Nothing here touches the real one."""

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
for _var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME'):
    os.environ.setdefault(_var, tempfile.mkdtemp(prefix=f'spark-controller-{_var.lower()}-'))


def put(path: str, value) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(str(value) + '\n')


def chip(root: str, folder: str, name: str, **files) -> str:
    """Make <root>/<folder>/ with a name file and the given files ('temp1_input': 45000)."""
    base = os.path.join(root, folder)
    put(os.path.join(base, 'name'), name)
    for filename, value in files.items():
        put(os.path.join(base, filename), value)
    return base


def fake_tree(root: str) -> None:
    """A desktop like the owner's: CPU, a motherboard chip with fan headers, an AMD GPU."""
    chip(root, 'hwmon2', 'k10temp', temp1_input=52000, temp1_label='Tctl', temp2_input=45000,
         temp2_label='Tccd1')
    chip(root, 'hwmon3', 'amdgpu', temp1_input=61000, temp1_label='edge', temp2_input=70000,
         temp2_label='junction', fan1_input=0, pwm1=0, pwm1_enable=2, pwm1_max=255)
    chip(root, 'hwmon10', 'nct6799', fan1_input=900, pwm1=100, pwm1_enable=5,
         fan2_input=1100, pwm2=120, pwm2_enable=5, fan3_input=0, temp1_input=33000,
         temp1_label='SYSTIN')
    # an NVMe drive with no fans, and a folder without a name (ignored)
    chip(root, 'hwmon4', 'nvme', temp1_input=40000, temp1_label='Composite')
    os.makedirs(os.path.join(root, 'hwmon9'), exist_ok=True)
