from gi.repository import Gtk
from gi.repository import Gio
from gi.repository import Adw
from gi.repository import GObject
import logging
import re

logger = logging.getLogger("Texwriter")


class LogViewer(Gtk.ListBox):
    __gtype_name__ = "LogViewer"

    def __init__(self):
        super().__init__()
        self.file = None
        self.add_css_class("boxed-list")
        self.set_margin_start(20)
        self.set_margin_end(20)
        self.set_margin_top(10)
        self.set_vexpand(False)
        self.set_valign(Gtk.Align.START)

    def load_file(self, file=None):
        """Open File from command line or open / open recent etc."""
        logger.info("Opening %s", file.get_uri())
        file.load_contents_async(None, self.load_file_complete)

    def load_file_complete(self, file, result):
        success, contents, msg = file.load_contents_finish(result)
        if not success:
            path = file.peek_path()
            toast = Adw.Toast.new("Unable to load log file")
            toast.set_timeout(2)
            self.toastoverlay.add_toast(toast)
            logger.warning(f"Unable to open log file at {path}: msg")
            return
        try:
            text = contents.decode('utf-8')
        except UnicodeError as err:
            path = file.peek_path()
            toast = Adw.Toast.new("The log file is not UTF-8 encoded")
            toast.set_timeout(2)
            self.toastoverlay.add_toast(toast)
            logger.warning(f"Unable to load the contents of the log file at {path}: the file is not encoded with UTF-8")
            return

        badbox_re  = re.compile("^((?:Over|Under)full \\\\[hv]box).* ([0-9]+)--[0-9]+.*\n",re.MULTILINE)
        warning_re = re.compile("^LaTeX Warning: (Reference|Citation) '(.*)'.* ([0-9]*)\.\n",re.MULTILINE)
        error_re   = re.compile("^! (.*)\.\nl\.([0-9]*) (.*$)",re.MULTILINE)

        for match in re.finditer(badbox_re, text):
            title = match.group(1)
            line = int(match.group(2))
            self.add_row(title, line)

        for match in re.finditer(warning_re, text):
            title = "Undefined " + match.group(1).lower() + ": " + match.group(2)
            line = int(match.group(3))
            self.add_row(title, line)

        for match in re.finditer(error_re, text):
            title = match.group(1) + ": " + match.group(3)
            line = int(match.group(2))
            self.add_row(title, line)


    def add_row(self, title, line):
        row = Adw.ActionRow.new()
        row.set_activatable(True)
        row.line = line
        row.set_title(title)
        self.append(row)

