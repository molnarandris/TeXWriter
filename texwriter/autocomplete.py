from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GObject
import xml.etree.ElementTree as ET

class AutocompletePopover(Gtk.Popover):
    __gtype_name__ = 'AutocompletePopover'

    def __init__(self, parent):
        super().__init__()
        self.set_parent(parent)
        self.set_autohide(False)
        self.is_active = False
        self.listbox = Gtk.ListBox()
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.listbox)
        scroll.set_propagate_natural_width(True)
        self.set_child(scroll)
        self.commands = []

        controller = Gtk.EventControllerKey()
        controller.connect("key_pressed", self.key_press_cb)
        parent.add_controller(controller)

        controller = Gtk.EventControllerKey()
        controller.connect("key_released", self.key_release_cb)
        parent.add_controller(controller)

        controller = Gtk.GestureClick()
        controller.connect("released", self.button_release_cb)
        #parent.get_root().add_controller(controller)

        packages = ["tex", "latex-document", "amsmath", "amsthm"]
        for pkg in packages:
            file = Gio.File.new_for_uri(f"resource:///com/github/molnarandris/texwriter/completion/{pkg}.xml")
            contents = file.load_contents()
            text = contents[1].decode('utf-8')
            root = ET.fromstring(text)
            for child in root:
                a = child.attrib
                cmd = {'package': pkg,
                       'command': a['text'],
                       'description': _(a['description']),
                       'lowpriority': True if a['lowpriority'] == "True" else False,
                       'dotlabels': a['dotlabels']}
                self.commands.append(cmd)

        for cmd in self.commands:
            row = Gtk.ListBoxRow()
            row.set_halign(Gtk.Align.START)
            row.text = cmd['command']
            row.set_child(Gtk.Label.new(row.text))
            self.listbox.append(row)
        self.selected_row = None

    def key_press_cb(self, controller, keyval, keycode, state):
        if not self.is_active and keyval != Gdk.KEY_backslash: return
        match keyval:
            case Gdk.KEY_backslash:
                self.activate()
                return False
            case Gdk.KEY_Escape | Gdk.KEY_space:
                self.deactivate()
                return False
            case Gdk.KEY_Return | Gdk.KEY_Tab:
                self.activate_selected_row()
                return True
            case Gdk.KEY_Down:
                self.select_next_row()
                return True
            case Gdk.KEY_Up:
                self.select_prev_row()
                return True
            case _:
                return False

    def key_release_cb(self, controller, keyval, keycode, state):
        if keyval in [Gdk.KEY_Down, Gdk.KEY_Down]:
            return
        if not self.is_active: return
        self.listbox.invalidate_filter()
        self.listbox.set_filter_func(self.filter_func)
        empty = True
        for row in self.listbox:
            if self.filter_func(row):
                self.listbox.select_row(row)
                empty = False
                break
        if empty:
            self.deactivate()
        else:
            self.update_position()

    def activate(self):
        self.update_position()
        self.popup()
        row = self.listbox.get_row_at_index(0)
        self.listbox.select_row(row)
        self.is_active = True
        buffer = self.get_parent().get_buffer()
        it = buffer.get_iter_at_mark(buffer.get_insert())
        mark = Gtk.TextMark.new("autocomplete", left_gravity=True)
        buffer.add_mark(mark,it)

    def deactivate(self):
        self.popdown()
        buffer = self.get_parent().get_buffer()
        mark = buffer.get_mark("autocomplete")
        buffer.delete_mark(mark)
        self.is_active = False

    def activate_selected_row(self):
        row = self.listbox.get_selected_row()
        buffer = self.get_parent().get_buffer()
        text = self.get_typed_text()
        buffer.insert_at_cursor(row.text.lstrip(text))
        self.deactivate()

    def get_typed_text(self):
        buffer = self.get_parent().get_buffer()
        mark = buffer.get_mark("autocomplete")
        start_it = buffer.get_iter_at_mark(mark)
        end_it = buffer.get_iter_at_mark(buffer.get_insert())
        text = buffer.get_text(start_it, end_it, include_hidden_chars=False)
        return text

    def filter_func(self, row):
        text = self.get_typed_text()
        if row.text.find(text) == -1:
            return False
        else:
            return True

    def select_next_row(self):
        n = self.listbox.get_selected_row().get_index()
        row = self.listbox.get_row_at_index(n+1)
        if row: self.listbox.select_row(row)

    def select_prev_row(self):
        n = self.listbox.get_selected_row().get_index()
        row = self.listbox.get_row_at_index(n-1)
        if row: self.listbox.select_row(row)

    def button_release_cb(self, window, n, x, y):
        if not self.is_active: return
        self.deactivate()

    def update_position(self):
        textview = self.get_parent()
        buffer = textview.get_buffer()
        it = buffer.get_iter_at_mark(buffer.get_insert())
        buf_rect = textview.get_iter_location(it)
        rect = Gdk.Rectangle()
        x, y = textview.buffer_to_window_coords(Gtk.TextWindowType.TEXT, buf_rect.x,buf_rect.y)
        rect.x, rect.y = textview.translate_coordinates(textview, x,y)
        rect.width = buf_rect.width
        rect.height = buf_rect.height
        self.set_pointing_to(rect)
