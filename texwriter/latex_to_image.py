from gi.repository import GLib
from gi.repository import Gio
from gi.repository import GObject
from gi.repository import Gtk


class LatexToImage(GObject.Object):
    TEX_HEADER = r"""\documentclass[convert]{standalone}
    \begin{document}"""

    TEX_FOOTER = r"""\end{document}"""

    PWD = GLib.get_tmp_dir() + "com.github.molnarandris.texwriter/"

    def __init__(self, text):
        super().__init__()
        self.compile_task = None
        self.text = self.TEX_HEADER + text + self.TEX_FOOTER

    def compile_async(self, cancellable, callback, user_data = None):
        if self.compile_task is not None:
            error = GLib.Error("Already compiling",
                               Gio.io_error_quark(),
                               Gio.IOErrorEnum.PENDING)
            Gio.Task.report_error(self, callback, user_data, None, error)
            return

        cancellable = cancellable or Gio.Cancellable()

        # Python bindings for Gio.Task do not pass user_data to the callback.
        # So, we need to manually pass those to the callback by using a new
        # function as callback to `Gio.Task.new()`. This new function will call
        # the original callback with appropriate user_data.
        original_callback = callback
        def callback(source_object, result, not_user_data):
            original_callback(source_object, result, user_data)

        task = Gio.Task.new(self, cancellable, callback, user_data)
        self.compile_task = task

        bytes = GLib.Bytes.new(self.text.encode('utf-8'))
        self.file, iostream = Gio.File.new_tmp('XXXXXX.tex')
        self.file.replace_contents_bytes_async(contents=bytes,
                                         etag=None,
                                         make_backup = False,
                                         flags = Gio.FileCreateFlags.NONE,
                                         cancellable=cancellable,
                                         callback=self.compile_cb1,
                                         user_data=task)

    def compile_cb1(self, file, result, task):
        try:
            file.replace_contents_finish(result)
        except GLib.Error as err:
            err.message = "Writing file failed: " + self.file.get_path()
            task.return_error(err)
            return

        pwd = self.file.get_parent().get_path()
        cmd = ['flatpak-spawn', '--host', '--directory=' + pwd, 'pdflatex', '--shell-escape',
               '--interaction=nonstopmode',   self.file.get_path()]
        flags = Gio.SubprocessFlags.STDOUT_PIPE
        flags = flags | Gio.SubprocessFlags.STDERR_PIPE
        proc = Gio.Subprocess.new(cmd, flags)
        cancellable = task.get_cancellable()
        proc.communicate_utf8_async(None, cancellable, self.compile_cb2, task)

    def compile_cb2(self, proc, result, task):
        try:
            success, out_str, err_str = proc.communicate_utf8_finish(result)
        except GLib.Error as err:
            task.return_error(err)
            return

        #print("OUTPUT of: " + self.file.get_path() + "\n" + out_str + "\n")
        #print("STDERR of: " + self.file.get_path() + "\n" + err_str + "\n")

        path = self.file.get_path()[:-4]
        self.img = Gtk.Image.new_from_file(path + ".png")
        for ext in ["aux", "log", "tex", "pdf", "png"]:
            f = Gio.File.new_for_path(path + "." + ext)
            f.delete(None)


        if success is False:
            err = GLib.Error("Compilation failed: " + path + ".tex")
            task.return_error(err)
            return
        task.return_boolean(True)

    def compile_finish(self, result):
        # clean up all temporary files
        # find out if operation was successful
        # if yes, return the Gtk Image generated
        # if not, raise the error
        try:
            success = result.propagate_boolean()
        finally:
            # clean up files
            pass

        if not success:
            raise Error("Compilation failed")

        return self.img

