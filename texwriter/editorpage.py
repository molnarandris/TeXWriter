import logging
import re
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import Adw
from .autocomplete import AutocompletePopover
from .parser import LatexParser
from .latex_to_image import LatexToImage

TEXT_ONLY = Gtk.TextSearchFlags.TEXT_ONLY
logger = logging.getLogger("Texwriter")

@Gtk.Template(resource_path="/com/github/molnarandris/texwriter/ui/editorpage.ui")
class EditorPage(Gtk.ScrolledWindow):
    __gtype_name__ = "EditorPage"

    textview = Gtk.Template.Child()
    title = GObject.Property(type=str, default="New Document")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.compile_task = None
        self.save_task = None
        self.synctex_task = None
        self.open_task = None
        self.file = None

        self.popover = AutocompletePopover(self.textview)
        buffer = self.textview.get_buffer()
        buffer.connect("modified-changed", self.on_buffer_modified_changed)
        buffer.create_tag('highlight', background='red')

        self.parser = LatexParser(buffer)


    @property
    def modified(self):
        return self.textview.props.buffer.get_modified()

    def on_buffer_modified_changed(self, *_args):
        prefix = "• " if self.modified else ""
        self.props.title = prefix + self.display_name

    def open_async(self, file, cancellable, callback, *user_data):
        if self.open_task:
            self.open_task.get_cancellable().cancel()
        cancellable = cancellable or Gio.Cancellable()

        if callback is not None:
            original_callback = callback
            def callback(source_object, result, not_user_data):
                original_callback(source_object, result, user_data)

        task = Gio.Task.new(self, cancellable, callback, user_data)
        self.open_task = task

        if file is None:
            dialog = Gtk.FileDialog()
            win = self.get_root()
            dialog.open(win, cancellable, self.open_cb1, task)
        else:
            file.load_contents_async(cancellable, self.open_cb2, task)

    def open_cb1(self, dialog, response, task):
        try:
            file = dialog.open_finish(response)
        except GLib.Error as err:
            task.return_error(err)
        else:
            cancellable = task.get_cancellable()
            file.load_contents_async(cancellable, self.open_cb2, task)

    def open_cb2(self, file, result, task):
        try:
            success, contents, etag = file.load_contents_finish(result)
        except GLib.Error as err:
            task.return_error(err)
            return

        if not success:
            task.return_error(GLib.Error("Can't load file"))
            return

        try:
            text = contents.decode("utf-8")
        except UnicodeError:
            task.return_error(GLib.Error("Unable to decode file"))
            return

        buffer = self.textview.props.buffer
        buffer.props.text = text
        self.file = file
        buffer.set_modified(False)  # This also updates the title
        task.return_boolean(True)

    def open_finish(self, result):
        self.open_task = None

        if not Gio.Task.is_valid(result, self):
            err = GLib.Error("Synctex failed",
                             GLib.Spawn_error_quark(),
                             GLib.SpawnErrorEnum.FAILED)
            raise(err)

        return result.propagate_boolean()

    def save_file_async(self, cancellable, callback, user_data):
        if self.save_task:
            assert self.save_task.get_cancellable is not None
            self.save_task.get_cancellable().cancel()
        cancellable = cancellable or Gio.Cancellable()

        if callback is not None:
            original_callback = callback
            def callback(source_object, result, not_user_data):
                original_callback(source_object, result, user_data)

        task = Gio.Task.new(self, cancellable, callback, user_data)
        self.save_task = task

        buffer = self.textview.props.buffer
        start_it = buffer.get_start_iter()
        end_it = buffer.get_end_iter()
        text = buffer.get_text(start_it, end_it, False)
        bytes = GLib.Bytes.new(text.encode('utf-8'))

        self.file.replace_contents_bytes_async(contents=bytes,
                                               etag=None,
                                               make_backup=False,
                                               flags=Gio.FileCreateFlags.NONE,
                                               cancellable=cancellable,
                                               callback=self.save_file_cb,
                                               user_data=task)

    def save_file_cb(self, file, result, task):
        try:
            file.replace_contents_finish(result)
        except GLib.Error as err:
            task.return_error(err)
            return
        self.textview.get_buffer().set_modified(False)
        self.file = file
        self.title = self.display_name
        task.return_boolean(True)
        return

    def save_file_finish(self, result):
        self.save_cancellable = None

        if not Gio.Task.is_valid(result, self):
            err = GLib.Error("Synctex failed",
                             GLib.Spawn_error_quark(),
                             GLib.SpawnErrorEnum.FAILED)
            raise(err)
        return result.propagate_boolean()

    def compile_async(self, cancellable, callback, user_data=None):
        if self.compile_task:
            assert self.compile_task.get_cancellable is not None
            self.compile_task.get_cancellable().cancel()
        cancellable = cancellable or Gio.Cancellable()

        original_callback = callback
        def callback(source_object, result, not_user_data):
            original_callback(source_object, result, user_data)

        task = Gio.Task.new(self, cancellable, callback, user_data)
        self.synctex_task = task

        pwd = self.file.get_parent().get_path()
        cmd = ['flatpak-spawn', '--host', 'latexmk', '-synctex=1',
               '-interaction=nonstopmode', '-pdf', "-g",
               "--output-directory=" + pwd,
               self.file.get_path()]
        flags = Gio.SubprocessFlags.STDOUT_SILENCE
        flags = flags | Gio.SubprocessFlags.STDERR_SILENCE
        proc = Gio.Subprocess.new(cmd, flags)
        proc.wait_async(cancellable, self.compile_cb, task)

    def compile_cb(self, source, result, task):
        try:
            source.wait_finish(result)
        except GLib.Error as err:
            task.return_error(err)
            return
        if not source.get_successful():
            err = GLib.Error("Compilation failed",
                             GLib.Spawn_error_quark(),
                             GLib.SpawnErrorEnum.FAILED)
            task.return_error(err)
            return
        task.return_boolean(True)


    def compile_finish(self, result):
        self.compile_cancellable = None

        if not Gio.Task.is_valid(result, self):
            err = GLib.Error("Compilation failed",
                             GLib.Spawn_error_quark(),
                             GLib.SpawnErrorEnum.FAILED)
            raise err

        return result.propagate_boolean()

    def synctex_async(self, cancellable, callback, user_data):
        if self.synctex_task is not None:
            assert self.synctex_task.get_cancellable() is not None
            self.synctex_task.get_cancellable().cancel()
        cancellable = cancellable or Gio.Cancellable()

        # Python bindings for Gio.Task do not pass user_data to the callback.
        # So, we need to manually pass those to the callback by using a new
        # function as callback to `Gio.Task.new()`. This new function will call
        # the original callback with appropriate user_data.
        original_callback = callback
        def callback(source_object, result, not_user_data):
            original_callback(source_object, result, user_data)

        task = Gio.Task.new(self, cancellable, callback, user_data)
        self.synctex_task = task

        buffer = self.textview.props.buffer
        it = buffer.get_iter_at_mark(buffer.get_insert())
        path = self.file.get_path()
        pos = str(it.get_line()) + ":" + str(it.get_line_offset()) + ":" + path
        cmd = ['flatpak-spawn', '--host', 'synctex', 'view', '-i', pos, '-o', path]
        flags = Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE
        proc = Gio.Subprocess.new(cmd, flags)

        proc.communicate_utf8_async(None, cancellable, self.synctex_cb, task)

    def synctex_cb(self, source, result, task):
        try:
            success, stdout, stderr = source.communicate_utf8_finish(result)
        except GLib.Error as err:
            task.return_error(err)
            return

        if not success:
            err = GLib.Error("Synctex failed",
                             GLib.Spawn_error_quark(),
                             GLib.SpawnErrorEnum.FAILED)
            task.return_error(err)
            return

        record = "Page:(.*)\n.*\n.*\nh:(.*)\nv:(.*)\nW:(.*)\nH:(.*)"
        rectangles = []
        for match in re.findall(record, stdout):
            page = int(match[0])-1
            x = float(match[1])
            y = float(match[2])
            width = float(match[3])
            height = float(match[4])
            rectangles.append((width, height, x, y, page))
        task.rectangles = rectangles
        task.return_boolean(True)

    def synctex_finish(self, result):
        self.synctex_task = None

        if not Gio.Task.is_valid(result, self):
            err = GLib.Error("Synctex failed",
                             GLib.Spawn_error_quark(),
                             GLib.SpawnErrorEnum.FAILED)
            raise(err)

        result.propagate_boolean()
        return result.rectangles

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

    def convert_inline_math(self):
        buffer = self.textview.props.buffer
        it = buffer.get_start_iter()
        tag = buffer.props.tag_table.lookup("inline-math")
        if tag is None:
            return
        start = False
        while it.forward_to_tag_toggle(tag):
            start = not start
            if start:
                start_it = it.copy()
            else:
                text = buffer.get_text(start_it, it, False)
                converter = LatexToImage(text)
                mark = Gtk.TextMark.new(None, True)
                buffer.add_mark(mark, it)
                print(text)

                # This is bad: if compilation finishes early, we insert a
                # picture in buffer that invalidates out iterator.
                converter.compile_async(None, self.compile_finish, mark)

    def compile_finish(self, converter, result, mark):
        print(converter)
        try:
            img = converter.compile_finish(result)
        except GLib.Error as err:
            print("Inline math compilation has failed:", err)
            return

        paint = img.get_paintable()
        buffer = self.textview.props.buffer
        it = buffer.get_iter_at_mark(mark)
        buffer.insert_paintable(it, paint)

