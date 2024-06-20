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
from .autocomplete import AutocompletePopover

import sys
import re
import logging
logging.basicConfig(level=logging.NOTSET)
logger = logging.getLogger("Texwriter")

@Gtk.Template(resource_path='/com/github/molnarandris/texwriter/ui/window.ui')
class TexwriterWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'TexwriterWindow'

    paned = Gtk.Template.Child()
    textview = Gtk.Template.Child()
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
        self.textview.get_buffer().connect("modified-changed", self.on_buffer_modified_changed)
        self.title = "New Document"
        self.file = None
        self.force_close = False
        # Keep track whether there is an ongoing operation.
        # If yes, we have to cancel it before starting a new one.
        # Ongoing operation = cancellable is not None
        self.save_cancellable = None
        self.compile_cancellable = None
        self.pdfview.connect("synctex-back", lambda _, line: self.scroll_to(line))
        self.logview.connect("row-activated", lambda _, row: self.scroll_to(row.line))
        self.pdf_log_switch.connect("clicked", self.pdf_log_switch_cb)

        self.popover = AutocompletePopover(self.textview)

    def notify(self, str):
        toast = Adw.Toast.new(str)
        toast.set_timeout(2)
        self.toastoverlay.add_toast(toast)

    def open(self, file=None):
        if file is None:
            dialog = Gtk.FileDialog()
            dialog.open(self, None, self.open_dialog_complete)
        else:
            file.load_contents_async(None, self.open_complete)

    def open_dialog_complete(self, dialog, response):
        try:
            file = dialog.open_finish(response)
            file.load_contents_async(None, self.open_complete)
        except GLib.Error as err:
            if err.matches(Gtk.dialog_error_quark(), Gtk.DialogError.DISMISSED):
                return
            else:
                # FIXME: which file? Why?
                self.notify("Unable to open file")

    def open_complete(self, file, result):
        display_name = get_display_name(file)
        success, contents, _ = file.load_contents_finish(result)
        if not success:
            self.notify(f"Unable to load {display_name}")
            return
        try:
            text = contents.decode('utf-8')
        except UnicodeError as err:
            path = file.peek_path()
            self.notify(f"The file {display_name} is not UTF-8 encoded")
            return

        buffer = self.textview.get_buffer()
        buffer.set_text(text)
        buffer.set_modified(False)

        self.title = display_name
        self.set_title(display_name)
        self.file = file
        self.load_pdf()
        self.load_log()

    def load_pdf(self):
        pdfpath = self.file.get_path()[:-3] + "pdf"
        pdffile = Gio.File.new_for_path(pdfpath)
        self.pdfview.load_file(pdffile)

    def load_log(self):
        logpath = self.file.get_path()[:-3] + "log"
        logfile = Gio.File.new_for_path(logpath)
        self.logview.load_file(logfile)

    def save(self, callback=None):
        if self.file:
            self.save_file(self.file, callback)
            return
        self.save_as(callback)

    def save_as(self, callback=None):
        native = Gtk.FileDialog()
        native.save(self, None, self.on_save_response, callback)

    def on_save_response(self, dialog, result, callback):
        try:
            file = dialog.save_finish(result)
        except GLib.Error as err:
            if err.matches(Gtk.dialog_error_quark(), Gtk.DialogError.DISMISSED):
                return
            else:
                self.notify("Unable to save file")

        if file is not None:
            self.save_file(file, callback)

    def save_file(self, file, callback=None):
        buffer = self.textview.get_buffer()
        start = buffer.get_start_iter()
        end = buffer.get_end_iter()
        text = buffer.get_text(start, end, False)
        bytes = GLib.Bytes.new(text.encode('utf-8'))

        if self.save_cancellable:
            self.save_cancellable.cancel()
        self.save_cancellable = Gio.Cancellable()

        file.replace_contents_bytes_async(contents=bytes,
                                          etag=None,
                                          make_backup=False,
                                          flags=Gio.FileCreateFlags.NONE,
                                          cancellable=self.save_cancellable,
                                          callback=self.save_file_complete,
                                          user_data=callback)

    def save_file_complete(self, file, result, callback):
        display_name = get_display_name(file)
        try:
            file.replace_contents_finish(result)
            self.textview.get_buffer().set_modified(False)
            self.file = file
            self.title = display_name
            self.set_title(display_name)
        except:
            self.notify(f"Unable to save {display_name}")

        self.save_cancellable = None
        if callback:
            callback()

    def compile(self):
        if self.compile_cancellable: self.compile_cancellable.cancel()
        self.cancellable = None

        # If needs saving, save first, then compile.
        if self.textview.get_buffer().get_modified():
            self.save(self.compile)
        # Otherwise we can proceed with compiling
        else:
            self.cancellable = Gio.Cancellable()
            pwd = self.file.get_parent().get_path()
            cmd = ['flatpak-spawn', '--host', 'latexmk', '-synctex=1',
                   '-interaction=nonstopmode', '-pdf', "-g",
                   "--output-directory=" + pwd,
                   self.file.get_path()]
            flags = Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE
            proc = Gio.Subprocess.new(cmd, flags)
            proc.wait_async(cancellable=self.cancellable,
                            callback=self.compile_complete)

    def compile_complete(self, source, result):
        try:
            source.wait_finish(result)
        except GLib.Error as err:
            if err.matches(Gio.io_error_quark(), GLib.IOErrorEnum.CANCELLED):
                pass
            else:
                raise
        finally:
            self.compile_cancellable = None

        self.load_log()
        if source.get_successful():
            self.load_pdf()
            self.result_stack.set_visible_child_name("pdf")
            self.synctex_fwd()
        else:
            display_name = get_display_name(self.file)
            self.notify(f"Compilation of {display_name} failed")
            self.result_stack.set_visible_child_name("log")

    def synctex_fwd(self):
        buffer = self.textview.get_buffer()
        it = buffer.get_iter_at_mark(buffer.get_insert())
        path = self.file.get_path()
        pos = str(it.get_line()) + ":" + str(it.get_line_offset()) + ":" + path
        cmd = ['flatpak-spawn', '--host', 'synctex', 'view', '-i', pos, '-o', path]
        flags = Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE
        proc = Gio.Subprocess.new(cmd, flags)
        proc.communicate_utf8_async(None, None, self.synctex_complete)

    def synctex_complete(self, source, result):
        success, stdout, stderr = source.communicate_utf8_finish(result)
        record = "Page:(.*)\n.*\n.*\nh:(.*)\nv:(.*)\nW:(.*)\nH:(.*)"
        for match in re.findall(record, stdout):
            page = int(match[0])-1
            x = float(match[1])
            y = float(match[2])
            width = float(match[3])
            height = float(match[4])
            self.pdfview.synctex_fwd(width, height, x, y, page)

    def scroll_to(self, line, offset=0):
        buffer = self.textview.get_buffer()
        _, it = buffer.get_iter_at_line(line)
        self.textview.scroll_to_iter(it, 0.3, False, 0, 0)
        buffer.place_cursor(it)
        self.textview.grab_focus()

    def do_close_request(self):
        if self.textview.get_buffer().get_modified() and not self.force_close:
            dialog = Adw.AlertDialog.new(_("Save Changes?"),
                                         _("“%s” contains unsaved changes. " +
                                           "If you don’t save, " +
                                           "all your changes will be " +
                                           "permanently lost.") % self.title
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
            settings.set_string("file", self.file.get_path())
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

    def on_buffer_modified_changed(self, *_args):
        modified = self.textview.get_buffer().get_modified()
        if modified:
            prefix = "• "
        else:
            prefix = ""
        self.set_title(prefix + self.title)

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

def get_display_name(file):
    info = file.query_info("standard::display-name",
                           Gio.FileQueryInfoFlags.NONE)
    if info:
        display_name = info.get_attribute_string("standard::display-name")
    else:
        display_name = file.get_basename()
    return display_name

