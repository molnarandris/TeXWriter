import logging
import re
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import Adw
from .autocomplete import AutocompletePopover

TEXT_ONLY = Gtk.TextSearchFlags.TEXT_ONLY
logger = logging.getLogger("Texwriter")

@Gtk.Template(resource_path="/com/github/molnarandris/texwriter/ui/editorpage.ui")
class EditorPage(Gtk.ScrolledWindow):
    __gtype_name__ = "EditorPage"

    textview = Gtk.Template.Child()
    title = GObject.Property(type=str, default="New Document")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.compile_cancellable = None
        self.save_cancellable = None
        self.load_cancellable = None
        self.file = None

        self.popover = AutocompletePopover(self.textview)
        buffer = self.textview.get_buffer()
        buffer.connect("modified-changed", self.on_buffer_modified_changed)
        buffer.create_tag('highlight', background='red')


    @property
    def modified(self):
        return self.textview.props.buffer.get_modified()

    def on_buffer_modified_changed(self, *_args):
        prefix = "• " if self.modified else ""
        self.props.title = prefix + self.display_name

    def load_file(self, callback=None):
        if self.load_cancellable is not None: self.load_cancellable.cancel()
        self.load_cancellable = Gio.Cancellable()
        self.file.load_contents_async(self.load_cancellable,
                                      self.load_file_complete,
                                      callback)

    def load_file_complete(self, file, result, callback):
        success, contents, _ = file.load_contents_finish(result)
        if success:
            try:
                text = contents.decode("utf-8")
            except UnicodeError as err:
                win = self.props.root
                win.notify(f"The file {self.display_name} is not UTF-8 encoded")
            else:
                buffer = self.textview.props.buffer
                buffer.props.text = text
                buffer.set_modified(False)  # This also updates the title :D
        else:
            win = self.props.root
            win.notify(f"Unable to load file {self.display_name}")
        if callback is not None: callback(self)


    def save_file(self, callback=None):
        buffer = self.textview.props.buffer
        start = buffer.get_start_iter()
        end = buffer.get_end_iter()
        text = buffer.get_text(start, end, False)
        bytes = GLib.Bytes.new(text.encode('utf-8'))

        if self.save_cancellable:
            self.save_cancellable.cancel()
        self.save_cancellable = Gio.Cancellable()

        self.file.replace_contents_bytes_async(contents=bytes,
                                               etag=None,
                                               make_backup=False,
                                               flags=Gio.FileCreateFlags.NONE,
                                               cancellable=self.save_cancellable,
                                               callback=self.save_file_complete,
                                               user_data=callback)

    def save_file_complete(self, file, result, callback):
        self.save_cancellable = None
        try:
            file.replace_contents_finish(result)
        except:
            win = self.props.root
            win.notify(f"Unable to save {self.display_name}")
        else:
            self.textview.get_buffer().set_modified(False)
            self.file = file
            self.title = self.display_name
        finally:
            if callback: callback()

    def compile_async(self, callback):
        if self.compile_cancellable:
            self.compile_cancellable.cancel()
        self.compile_cancellable = Gio.Cancellable()
        pwd = self.file.get_parent().get_path()
        cmd = ['flatpak-spawn', '--host', 'latexmk', '-synctex=1',
               '-interaction=nonstopmode', '-pdf', "-g",
               "--output-directory=" + pwd,
               self.file.get_path()]
        flags = Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE
        proc = Gio.Subprocess.new(cmd, flags)
        proc.wait_async(cancellable=self.compile_cancellable,
                        callback=callback,
                        user_data=self)

    def compile_finish(self, source, result):
        self.compile_cancellable = None
        try:
            source.wait_finish(result)
        except GLib.Error as err:
            if err.matches(Gio.io_error_quark(), GLib.IOErrorEnum.CANCELLED):
                logging.warning("Compiling file was cancelled: %s", err.message)
            else:
                raise err
        if not source.get_successful():
            raise Exception("Compilation failed")

    def synctex(self, callback):
        buffer = self.textview.props.buffer
        it = buffer.get_iter_at_mark(buffer.get_insert())
        path = self.file.get_path()
        pos = str(it.get_line()) + ":" + str(it.get_line_offset()) + ":" + path
        cmd = ['flatpak-spawn', '--host', 'synctex', 'view', '-i', pos, '-o', path]
        flags = Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE
        proc = Gio.Subprocess.new(cmd, flags)
        proc.communicate_utf8_async(None, None, self.synctex_complete, callback)

    def synctex_complete(self, source, result, callback):
        success, stdout, stderr = source.communicate_utf8_finish(result)
        if not success:
            win = self.props.root
            win.notify("Could not run synctex")
        record = "Page:(.*)\n.*\n.*\nh:(.*)\nv:(.*)\nW:(.*)\nH:(.*)"
        for match in re.findall(record, stdout):
            page = int(match[0])-1
            x = float(match[1])
            y = float(match[2])
            width = float(match[3])
            height = float(match[4])
        callback(width, height, x, y, page)

    @property
    def display_name(self, file=None):
        if file is None: file = self.file
        if file is None:
            return "New File"
        info = file.query_info("standard::display-name",
                               Gio.FileQueryInfoFlags.NONE)
        if info:
            display_name = info.get_attribute_string("standard::display-name")
        else:
            display_name = file.get_basename()
        return display_name

    def scroll_to(self, line, word=None):
        buffer = self.textview.props.buffer
        _, it = buffer.get_iter_at_line(line)
        bound = it.copy()
        bound.forward_to_line_end()
        if word:
            result = it.forward_search(word, TEXT_ONLY, bound)
            if result is not None:
                buffer.apply_tag_by_name('highlight', *result)
                GLib.timeout_add(500, lambda: buffer.remove_tag_by_name('highlight',*result))
                it = result[0]
        self.textview.scroll_to_iter(it, 0.3, False, 0, 0)
        buffer.place_cursor(it)
        self.textview.grab_focus()

