"""Import this first: every folder the app uses becomes a temporary one, and the pipeline runs
on a test pattern. Nothing outside the temporary folder is written, and the real service's
control socket is never touched."""

import atexit
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

ROOT = tempfile.mkdtemp(prefix='spark-clips-test-')
for var, sub in (('HOME', ''), ('XDG_CONFIG_HOME', 'config'), ('XDG_STATE_HOME', 'state'),
                 ('XDG_CACHE_HOME', 'cache'), ('XDG_DATA_HOME', 'data'),
                 ('XDG_RUNTIME_DIR', 'run'), ('SPARK_CLIPS_SHM', 'shm')):
    os.environ[var] = os.path.join(ROOT, sub) if sub else ROOT
os.environ['SPARK_CLIPS_FAKE'] = '1'
os.environ['SPARK_CLIPS_REDUCED_MOTION'] = '1'
os.environ.pop('SPARK_CLIPS_ENCODER', None)
atexit.register(shutil.rmtree, ROOT, True)


def reset() -> None:
    """Empty the temporary folders between tests."""
    for sub in os.listdir(ROOT):
        shutil.rmtree(os.path.join(ROOT, sub), ignore_errors=True)


def have_display() -> bool:
    return bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))
