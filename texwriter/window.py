# window.py
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

from gi.repository import Adw
from gi.repository import Gtk
from gi.repository import Gio
from gi.repository import GLib

import sys
import logging
logging.basicConfig(level=logging.NOTSET)
logger = logging.getLogger("Texwriter")

@Gtk.Template(resource_path='/com/github/molnarandris/texwriter/ui/window.ui')
class TexwriterWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'TexwriterWindow'

    paned = Gtk.Template.Child()
    textview = Gtk.Template.Child()
    toastoverlay = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Save and restore window geometry
        settings = Gio.Settings.new("com.github.molnarandris.texwriter")
        settings.bind("width", self, "default-width", Gio.SettingsBindFlags.DEFAULT)
        settings.bind("height", self, "default-height", Gio.SettingsBindFlags.DEFAULT)
        settings.bind("maximized", self, "maximized", Gio.SettingsBindFlags.DEFAULT)
        settings.bind("paned-position", self.paned, "position", Gio.SettingsBindFlags.DEFAULT)

        # Set up window actions
        action = Gio.SimpleAction.new("open", None)
        action.connect("activate", self.open_document)
        self.add_action(action)

        action = Gio.SimpleAction.new("save", None)
        action.connect("activate", self.on_save_action)
        self.add_action(action)

        action = Gio.SimpleAction.new("compile", None)
        action.connect("activate", self.compile_document)
        self.add_action(action)

        action = Gio.SimpleAction.new("synctex-fwd", None)
        action.connect("activate", self.compile_document)
        self.add_action(action)

        # Setting paned resize-start-child and resize-end-child True
        # makes the paned to keep the relative position at resize.
        # However, this doesn't work from the ui file.
        self.paned.set_resize_start_child(True)
        self.paned.set_resize_end_child(True)

        # TODO: override textbuffer's do_modified_changed.
        self.textview.get_buffer().connect("modified-changed", self.on_buffer_modified_changed)
        self.title = "New Document"
        self.file = None

    def open_document(self, _action, _value):

        dialog = Gtk.FileDialog()
        dialog.open(self, None, self.open_document_complete)

    def open_document_complete(self, dialog, response):
        try:
            file = dialog.open_finish(response)
            self.get_application().open([file], "")
        except GLib.Error as err:
            if err.matches(Gtk.dialog_error_quark(), Gtk.DialogError.DISMISSED):
                logger.info("File selection was dismissed: %s", err.message)
                return
            else:
                # FIXME: which file? Why?
                toast = Adw.Toast.new("Unable to open file")
                toast.set_timeout(2)
                self.toastoverlay.add_toast(toast)
                logger.warning(f"Unable to open file")

    def load_file(self, file=None):
        """Open File from command line or open / open recent etc."""
        logger.info("Opening %s", file.get_uri())

        file.load_contents_async(None, self.load_file_complete)

    def load_file_complete(self, file, result):
        info = file.query_info("standard::display-name", Gio.FileQueryInfoFlags.NONE)
        if info:
            display_name = info.get_attribute_string("standard::display-name")
        else:
            display_name = file.get_basename()

        contents = file.load_contents_finish(result)
        if not contents[0]:
            path = file.peek_path()
            toast = Adw.Toast.new("Unable to load file")
            toast.set_timeout(2)
            self.toastoverlay.add_toast(toast)
            logger.warning(f"Unable to open {path}: {contents[1]}")
            return
        try:
            text = contents[1].decode('utf-8')
        except UnicodeError as err:
            path = file.peek_path()
            toast = Adw.Toast.new("The file is not UTF-8 encoded")
            toast.set_timeout(2)
            self.toastoverlay.add_toast(toast)
            logger.warning(f"Unable to load the contents of {path}: the file is not encoded with UTF-8")
            return

        buffer = self.textview.get_buffer()
        buffer.set_text(text)
        buffer.set_modified(False)

        self.title = display_name
        self.set_title(display_name)
        self.file = file

    def on_save_action(self, _action, _value):
        if self.file:
            self.save_file(self.file)
            return
        native = Gtk.FileDialog()
        native.save(self, None, self.on_save_response)

    def on_save_response(self, dialog, result):
        file = dialog.save_finish(result)
        if file is not None:
            self.save_file(file)

    def save_file(self, file):
        buffer = self.textview.get_buffer()
        start = buffer.get_start_iter()
        end = buffer.get_end_iter()
        text = buffer.get_text(start, end, False)
        bytes = GLib.Bytes.new(text.encode('utf-8'))

        file.replace_contents_bytes_async(bytes,
                                          None,
                                          False,
                                          Gio.FileCreateFlags.NONE,
                                          None,
                                          self.save_file_complete)

    def save_file_complete(self, file, result):
        res = file.replace_contents_finish(result)
        info = file.query_info("standard::display-name",
                               Gio.FileQueryInfoFlags.NONE)
        if info:
            display_name = info.get_attribute_string("standard::display-name")
        else:
            display_name = file.get_basename()
        if res:
            self.textview.get_buffer().set_modified(False)
            self.file = file
        else:
            toast = Adw.Toast.new(f"Unable to save {display_name}")
            toast.set_timeout(2)
            self.toastoverlay.add_toast(toast)
            logger.warning(f"Unable to save {display_name}")

    def compile_document(self, _action, _value):
        pass

    def syntex_fwd(self, _action, _value):
        pass

    def on_buffer_modified_changed(self, *_args):
        modified = self.textview.get_buffer().get_modified()
        logger.info(f"Modified callback, {modified}")
        if modified:
            prefix = "• "
        else:
            prefix = ""
        self.set_title(prefix + self.title)
