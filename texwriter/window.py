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
from .resultviewer import ResultViewer

import sys
import re
import logging
logging.basicConfig(level=logging.NOTSET)
logger = logging.getLogger("Texwriter")

@Gtk.Template(resource_path='/com/github/molnarandris/texwriter/ui/window.ui')
class TexwriterWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'TexwriterWindow'

    paned = Gtk.Template.Child()
    tabview = Gtk.Template.Child()
    toastoverlay = Gtk.Template.Child()
    pdf_log_switch = Gtk.Template.Child()
    result_stack = Gtk.Template.Child()
    title = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.result_stack.set_visible_child_name("empty")
        editorpage = EditorPage()
        self.tabview.append(editorpage)
        self.title_binding = editorpage.bind_property("title", self.title, "label")
        result_view = ResultViewer()
        editorpage.result_view = result_view
        self.editorpage = editorpage
        self.result_stack.add(result_view)
        self.result_stack.set_visible_child(result_view)
        self.pdf_log_switch.connect("clicked", self.pdf_log_switch_cb)


        # Save and restore window geometry
        # File loading is in main.py and saving is in do_close_request.
        settings = Gio.Settings.new("com.github.molnarandris.texwriter")
        settings.bind("width", self, "default-width", Gio.SettingsBindFlags.DEFAULT)
        settings.bind("height", self, "default-height", Gio.SettingsBindFlags.DEFAULT)
        settings.bind("maximized", self, "maximized", Gio.SettingsBindFlags.DEFAULT)
        settings.bind("paned-position", self.paned, "position", Gio.SettingsBindFlags.DEFAULT)

        # Set up window actions
        action = Gio.SimpleAction.new("open", None)
        action.connect("activate", lambda *_: self.open(None))
        self.add_action(action)

        action = Gio.SimpleAction.new("save", GLib.VariantType("b"))
        action.connect("activate", self.on_save_action)
        self.add_action(action)

        action = Gio.SimpleAction.new("compile", None)
        action.connect("activate", self.on_compile_action)
        self.add_action(action)

        action = Gio.SimpleAction.new("synctex-fwd", None)
        action.connect("activate", self.on_synctex_fwd_action)
        self.add_action(action)

        action = Gio.SimpleAction.new("convert-inline-math", None)
        action.connect("activate", self.on_convert_inline_math_action)
        self.add_action(action)

        # Setting paned resize-start-child and resize-end-child True
        # makes the paned to keep the relative position at resize.
        # However, this doesn't work from the ui file.
        self.paned.set_resize_start_child(True)
        self.paned.set_resize_end_child(True)

        # TODO: override textbuffer's do_modified_changed.
        self.title_binding = None
        self.tabview.connect("notify::selected-page", self.tab_page_change_cb)
        self.force_close = False
        # Keep track whether there is an ongoing operation.
        # If yes, we have to cancel it before starting a new one.
        # Ongoing operation = cancellable is not None
        self.save_cancellable = None
        self.compile_cancellable = None

    def tab_page_change_cb(self, psec):
        self.editorpage.unbind(self.title_binding)
        self.editorpage = self.tabview.props.selected_page
        self.title_binding = self.editorpage.bind_property("title", self.title, "label")

    def notify(self, str):
        toast = Adw.Toast.new(str)
        toast.set_timeout(2)
        self.toastoverlay.add_toast(toast)

    def open(self, file):
        # When there will be tabs: find out if open in current editorpage
        # Or create a new one and open it there
        editorpage = self.editorpage
        editorpage.open_async(file, None, self.open_complete)

    def open_complete(self, editorpage, result, *user_data):
        # I should call here open_complete
        try:
            editorpage.open_finish(result)
        except GLib.Error as err:
            self.notify("Can't open file: {err.message}")
            return
        result_view = editorpage.result_view
        pdfview = result_view.pdfview
        logview = result_view.logview
        pdfview.connect("synctex-back", lambda _, line, around, after: self.scroll_to(editorpage, line, after))
        logview.connect("row-activated", lambda _, row: self.scroll_to(editorpage, row.line, row.text))
        result_view.connect("notify::visible-child-name", self.stack_change_cb)
        # settings.bind("pdf-scale", self.pdfview, "scale", Gio.SettingsBindFlags.DEFAULT)

        self.load_pdf(editorpage)
        self.load_log(editorpage)

    def load_pdf(self, editor):
        pdfpath = editor.file.get_path()[:-3] + "pdf"
        pdffile = Gio.File.new_for_path(pdfpath)
        editor.result_view.pdfview.load_file(pdffile)

    def load_log(self, editor):
        logpath = editor.file.get_path()[:-3] + "log"
        logfile = Gio.File.new_for_path(logpath)
        editor.result_view.logview.load_file(logfile)

    def on_save_action(self, action, param):
        save_as = param == GLib.Variant("b", True)
        self.save(save_as)

    def save(self, save_as=False, callback=None):
        if save_as is True or not self.editorpage.file:
            native = Gtk.FileDialog()
            native.save(self, None, self.save_dialog_cb, callback)
        else:
            self.editorpage.save_file_async(None, self.save_complete, callback)

    def save_dialog_cb(self, dialog, result, callback):
        try:
            file = dialog.save_finish(result)
        except GLib.Error as err:
            if err.matches(Gtk.dialog_error_quark(), Gtk.DialogError.DISMISSED):
                return
            else:
                self.notify(f"Unable to save file: {err.message}")
        else:
            self.editorpage.file = file
            self.editorpage.save_file_async(None, self.save_complete, callback)

    def save_complete(self, editorpage, result, callback):
        try:
            editorpage.save_file_finish(result)
        except GLib.Error as err:
            self.notify(f"Unable to save file: {err.message}")

        if callback is not None:
            callback()



    def on_compile_action(self, action, param):
        self.compile()

    # TODO: check gnome builder for chained actions. Builders run button is similar
    # Look at    gnome-builder/src/libide/gui/ide-run-button.c
    # Also at gnome-builder/src/libide/foundry/ide-run-manager.c
    def compile(self):
        editor = self.editorpage
        # If needs saving, save first, then compile.
        if editor.modified:
            self.save(callback=self.compile)
            return
        editor.compile_async(None, self.compile_complete)

    def compile_complete(self, editor, result, user_data):
        try:
            editor.compile_finish(result)
        except GLib.Error as err:
            display_name = editor.display_name
            self.notify(f"Compilation of {display_name} failed: {err.message}")
            editor.result_view.set_visible_child_name("log")
        else:
            self.load_pdf(editor)
            editor.result_view.set_visible_child_name("pdf")
            editor.synctex_async(None, self.synctex_complete, None)
        finally:
            self.load_log(editor)

    def on_synctex_fwd_action(self, action, param):
        editor = self.editorpage
        editor.synctex_async(None, self.synctex_complete, None)

    def synctex_complete(self, editor, result, user_data):
        try:
            rects = editor.synctex_finish(result)
        except GLib.Error as err:
            self.notify(err.message)
            return
        editor.result_view.set_visible_child_name("pdf")
        pdfview = editor.result_view.pdfview
        pdfview.synctex_fwd(rects)

    def scroll_to(self, editor, line, text=None):
        editor.scroll_to(line,text)

    def do_close_request(self):
        editor = self.editorpage
        if editor.modified and not self.force_close:
            dialog = Adw.AlertDialog.new(_("Save Changes?"),
                                         _("“%s” contains unsaved changes. " +
                                           "If you don’t save, " +
                                           "all your changes will be " +
                                           "permanently lost.") % editor.display_name
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
            if editor.file is not None:
                settings.set_string("file", editor.file.get_path())
            else:
                settings.set_string("file", "")
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
        result_view = self.editorpage.result_view
        match result_view.get_visible_child_name():
            case "pdf":
                result_view.set_visible_child_name("log")
            case "log":
                result_view.set_visible_child_name("pdf")
            case _:
                logger.warning("Pdf log switch button clicked while stack is not visible")

    def stack_change_cb(self, stack, property):
        if stack.props.visible_child_name == "pdf":
            self.pdf_log_switch.set_icon_name("issue-symbolic")
            self.pdf_log_switch.set_tooltip_text("View log")
        if stack.props.visible_child_name == "log":
            self.pdf_log_switch.set_icon_name("pdf-symbolic")
            self.pdf_log_switch.set_tooltip_text("View pdf")

    def on_convert_inline_math_action(self, action, param):
        self.editorpage.convert_inline_math()


