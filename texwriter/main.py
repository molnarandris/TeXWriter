# main.py
#
# Copyright 2024 András Molnár
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import sys
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Gio, Adw
from .window import TexwriterWindow


class TexwriterApplication(Adw.Application):
    """The main application singleton class."""

    def __init__(self):
        super().__init__(application_id='com.github.molnarandris.texwriter',
                         flags=Gio.ApplicationFlags.HANDLES_OPEN | Gio.ApplicationFlags.NON_UNIQUE)

        action = Gio.SimpleAction.new('quit', None)
        action.connect("activate", self.on_quit)
        self.add_action(action)

        action = Gio.SimpleAction.new('about', None)
        action.connect("activate", self.on_about_action)
        self.add_action(action)

        action = Gio.SimpleAction.new('preferences', None)
        action.connect("activate", self.on_preferences_action)
        self.add_action(action)

        # Shortcuts
        self.set_accels_for_action("app.quit", ['<primary>q'])
        self.set_accels_for_action("win.open", ['<primary>o'])
        self.set_accels_for_action("win.save", ['<primary>s'])
        self.set_accels_for_action("win.compile", ['F5'])


    def do_activate(self):
        """Called when the application is activated.

        We raise the application's main window, creating it if
        necessary.
        """
        win = self.props.active_window
        if not win:
            win = TexwriterWindow(application=self)
        win.present()

    def do_open(self, files, _n_files, _hint):
        self.activate()

        def window_filter(win):
            buf = win.textview.get_buffer()
            txt = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
            return txt == "" and not buf.get_modified()

        empty_windows = list(filter(window_filter, self.get_main_windows()))
        for i, file in enumerate(files):
            if i < len(empty_windows):
                win = empty_windows[i]
            else:
                win = TexwriterWindow(application=self)

            win.load_file(file)
            win.present()

    def on_about_action(self, widget, _):
        """Callback for the app.about action."""
        about = Adw.AboutWindow(transient_for=self.props.active_window,
                                application_name='texwriter',
                                application_icon='com.github.molnarandris.texwriter',
                                developer_name='András Molnár',
                                version='0.1.0',
                                developers=['András Molnár'],
                                copyright='© 2024 András Molnár')
        about.present()

    def on_preferences_action(self, widget, _):
        """Callback for the app.preferences action."""
        print('app.preferences action activated')

    def get_main_windows(self):
        return [window for window in self.get_windows() if isinstance(window, TexwriterWindow)]

    def on_quit(self, _action, _param):
        quit = True
        for window in self.get_windows():
            if window.do_close_request():
                quit = False
        if quit:
            self.quit()


def main(version):
    """The application's entry point."""
    app = TexwriterApplication()
    return app.run(sys.argv)
