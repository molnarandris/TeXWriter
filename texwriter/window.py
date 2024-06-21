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
from gi.repository import Gdk
from .pdfviewer import PdfViewer
from .logviewer import LogViewer
from .editorpage import EditorPage

import sys
import re
import logging
logging.basicConfig(level=logging.NOTSET)
logger = logging.getLogger("Texwriter")

@Gtk.Template(resource_path='/com/github/molnarandris/texwriter/ui/window.ui')
class TexwriterWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'TexwriterWindow'

    paned = Gtk.Template.Child()
    editorpage = Gtk.Template.Child()
    toastoverlay = Gtk.Template.Child()
    pdfview = Gtk.Template.Child()
    logview = Gtk.Template.Child()
    result_stack = Gtk.Template.Child()
    pdf_log_switch = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Save and restore window geometry
        # File loading is in main.py and saving is in do_close_request.
        settings = Gio.Settings.new("com.github.molnarandris.texwriter")
        settings.bind("width", self, "default-width", Gio.SettingsBindFlags.DEFAULT)
        settings.bind("height", self, "default-height", Gio.SettingsBindFlags.DEFAULT)
        settings.bind("maximized", self, "maximized", Gio.SettingsBindFlags.DEFAULT)
        settings.bind("paned-position", self.paned, "position", Gio.SettingsBindFlags.DEFAULT)
        settings.bind("pdf-scale", self.pdfview, "scale", Gio.SettingsBindFlags.DEFAULT)

        # Set up window actions
        action = Gio.SimpleAction.new("open", None)
        action.connect("activate", lambda *_: self.open())
        self.add_action(action)

        action = Gio.SimpleAction.new("save", None)
        action.connect("activate", lambda *_: self.save())
        self.add_action(action)

        action = Gio.SimpleAction.new("save-as", None)
        action.connect("activate", lambda *_: self.save_as())
        self.add_action(action)

        action = Gio.SimpleAction.new("compile", None)
        action.connect("activate", lambda *_: self.compile())
        self.add_action(action)

        action = Gio.SimpleAction.new("synctex-fwd", None)
        action.connect("activate", lambda *_: self.synctex_fwd())
        self.add_action(action)

        # Setting paned resize-start-child and resize-end-child True
        # makes the paned to keep the relative position at resize.
        # However, this doesn't work from the ui file.
        self.paned.set_resize_start_child(True)
        self.paned.set_resize_end_child(True)

        # TODO: override textbuffer's do_modified_changed.
        self.editorpage.bind_property("title", self, "title")
        self.force_close = False
        # Keep track whether there is an ongoing operation.
        # If yes, we have to cancel it before starting a new one.
        # Ongoing operation = cancellable is not None
        self.save_cancellable = None
        self.compile_cancellable = None
        self.pdfview.connect("synctex-back", lambda _, line: self.scroll_to(line))
        self.logview.connect("row-activated", lambda _, row: self.scroll_to(row.line))
        self.pdf_log_switch.connect("clicked", self.pdf_log_switch_cb)

    def notify(self, str):
        toast = Adw.Toast.new(str)
        toast.set_timeout(2)
        self.toastoverlay.add_toast(toast)

    def open(self, file=None):
        if file is None:
            dialog = Gtk.FileDialog()
            dialog.open(self, None, self.open_cb)
        else:
            self.editorpage.load_file_async(file, None, self.open_complete)

    def open_cb(self, dialog, response):
        try:
            file = dialog.open_finish(response)
            self.editorpage.load_file_async(file, None, self.open_complete)
        except GLib.Error as err:
            if err.matches(Gtk.dialog_error_quark(), Gtk.DialogError.DISMISSED):
                return
            else:
                # FIXME: which file? Why?
                self.notify("Unable to open file")

    def open_complete(self, file, result):
        try:
            self.editorpage.load_file_finish(file, result)
        except UnicodeError as err:
            self.notify(f"The file {self.editorpage.get_display_name()} is not UTF-8 encoded")
        except Exception as err:
            self.notify(err.value)

        self.load_pdf()
        self.load_log()

    def load_pdf(self):
        pdfpath = self.editorpage.file.get_path()[:-3] + "pdf"
        pdffile = Gio.File.new_for_path(pdfpath)
        self.pdfview.load_file(pdffile)

    def load_log(self):
        logpath = self.editorpage.file.get_path()[:-3] + "log"
        logfile = Gio.File.new_for_path(logpath)
        self.logview.load_file(logfile)

    def save(self, callback=None):
        if self.editorpage.file:
            self.editorpage.save_file_async(self.save_complete, callback)
        else:
            self.save_as(callback)

    def save_as(self, callback=None):
        native = Gtk.FileDialog()
        native.save(self, None, self.save_as_cb, callback)

    def save_as_cb(self, dialog, result, callback):
        try:
            file = dialog.save_finish(result)
        except GLib.Error as err:
            if err.matches(Gtk.dialog_error_quark(), Gtk.DialogError.DISMISSED):
                return
            else:
                self.notify("Unable to save file")

        if file is not None:
            self.editorpage.file = file
            self.editorpage.save_file_async(self.save_complete, callback)

    def save_complete(self, file, result, callback):
        try:
            self.editorpage.save_file_finish(file, result)
        except Exception as err:
            self.notify(err.value)
        if callback:
            callback()

    def compile(self):
        editor = self.editorpage
        # If needs saving, save first, then compile.
        if editor.modified:
            self.save(self.compile)
            return
        editor.compile_async(self.compile_complete)

    def compile_complete(self, source, result, editor):
        try:
            editor.compile_finish(source, result)
        except:
            display_name = editor.get_display_name()
            self.notify(f"Compilation of {display_name} failed")
            self.result_stack.set_visible_child_name("log")
        else:
            self.load_pdf()
            self.result_stack.set_visible_child_name("pdf")
            self.synctex_fwd()
        finally:
            self.load_log()

    def synctex_fwd(self):
        self.editorpage.synctex_async(self.synctex_complete)

    def synctex_complete(self, source, result):
        try:
            result = self.editorpage.synctex_finish(source,result)
        except:
            self.notify("Synctex error")
        width, height, x, y, page = result
        self.pdfview.synctex_fwd(width, height, x, y, page)

    def scroll_to(self, line, offset=0):
        editor = self.editorpage
        editor.scroll_to(line,offset)

    def do_close_request(self):
        editor = self.editorpage
        if editor.modified and not self.force_close:
            dialog = Adw.AlertDialog.new(_("Save Changes?"),
                                         _("“%s” contains unsaved changes. " +
                                           "If you don’t save, " +
                                           "all your changes will be " +
                                           "permanently lost.") % editor.get_display_name()
                                         )
            dialog.add_response("cancel", _("Cancel"))
            dialog.add_response("close", _("Discard"))
            dialog.add_response("save", _("Save"))
            dialog.set_response_appearance("close", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
            dialog.set_default_response("save")
            dialog.set_close_response("cancel")

            dialog.connect("response", self.close_request_complete)
            dialog.present(self)
            return True
        else:
            settings = Gio.Settings.new("com.github.molnarandris.texwriter")
            settings.set_string("file", editor.file.get_path())
            return False

    def close_request_complete(self, dialog, response):
        """Show dialog to prevent loss of unsaved changes
        """

        match response:
            case "cancel":
                return
            case "close":
                self.force_close = True
                self.close()
            case "save":
                self.save(callback=self.close)

    def pdf_log_switch_cb(self, button):
        match self.result_stack.get_visible_child_name():
            case "pdf":
                self.result_stack.set_visible_child_name("log")
                button.set_icon_name("pdf-symbolic")
                button.set_tooltip_text("View PDF")
            case "log":
                self.result_stack.set_visible_child_name("pdf")
                button.set_icon_name("issue-symbolic")
                button.set_tooltip_text("View log")
            case _:
                logger.warning("Pdf log switch button clicked while stack is not visible")
