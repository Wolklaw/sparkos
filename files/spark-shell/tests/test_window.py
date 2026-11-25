#!/usr/bin/env python3
"""A plain window with a known title and app id, for the headless session check."""

import sys

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk  # noqa: E402


def activate(app):
    win = Gtk.ApplicationWindow(application=app, title='Spark test window')
    win.set_default_size(480, 300)
    win.set_child(Gtk.Label(label='test window'))
    win.present()


app = Gtk.Application(application_id='dev.wolklaw.SparkTestWindow')
app.connect('activate', activate)
sys.exit(app.run([]))
