from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GObject
import xml.etree.ElementTree as ET


class AutocompletePopover(Gtk.Popover):
    __gtype_name__ = 'AutocompletePopover'

    def __init__(self, textview):
        super().__init__()
        self.set_parent(textview)
        self.set_autohide(True)
        self.is_active = False
        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.BROWSE)
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(listbox)
        scroll.set_propagate_natural_width(True)
        scroll.set_propagate_natural_height(True)
        self.set_child(scroll)
        self.commands = []
        self.textview = textview

        listbox.connect("row-activated", self.row_activated_cb)

        controller = Gtk.EventControllerKey()
        controller.set_propagation_phase(Gtk.PropagationPhase.BUBBLE)
        controller.connect("key_pressed", self.textview_key_press_cb)
        textview.add_controller(controller)

        controller = Gtk.EventControllerKey.new()
        controller.set_propagation_phase(Gtk.PropagationPhase.BUBBLE)
        controller.connect("key_pressed", self.key_press_cb)
        controller.connect("key_released", self.key_release_cb)
        self.add_controller(controller)

        self.connect("closed", self.closed_cb)

        self.listbox = listbox

        packages = ["tex", "latex-document", "amsmath", "amsthm"]
        for pkg in packages:
            file = Gio.File.new_for_uri(f"resource:///com/github/molnarandris/texwriter/completion/{pkg}.xml")
            contents = file.load_contents()
            text = contents[1].decode('utf-8')
            root = ET.fromstring(text)
            for child in root:
                if child.tag == "command":
                    a = child.attrib
                    cmd = {'package': pkg,
                           'command': a['text'],
                           'text': a['name'],
                           'description': _(a['description']),
                           'lowpriority': True if a['lowpriority'] == "True" else False,
                           'dotlabels': a['dotlabels']}
                    self.commands.append(cmd)
                if child.tag == "environment":
                    a = child.attrib
                    cmd = {'package': pkg,
                           'command': "\\begin{" + a['text'] + "}\n\\end{"+ a['text'] +"}",
                           'text': "\\begin{" + a['name'] + "}...\\end{"+ a['name'] +"}",
                           'description': _(a['description']),
                           'lowpriority': True if a['lowpriority'] == "True" else False,
                           'dotlabels': a['dotlabels']}
                    self.commands.append(cmd)

        for cmd in self.commands:
            if cmd['lowpriority'] is False:
                self.create_row(cmd)

        for cmd in self.commands:
            if cmd['lowpriority'] is True:
                self.create_row(cmd)

    def closed_cb(self, user_data):
        buffer = self.textview.get_buffer()
        mark = buffer.get_mark("autocomplete")
        mark is not None and buffer.delete_mark(mark)
        self.is_active = False

    def create_row(self, cmd):
        row = Gtk.ListBoxRow()
        row.set_halign(Gtk.Align.START)
        row.text = cmd['text']
        row.command = cmd['command']
        row.set_child(Gtk.Label.new(row.text))
        self.listbox.append(row)

    def textview_key_press_cb(self, controller, keyval, keycode, state):
        if not self.is_active and keyval == Gdk.KEY_backslash:
            self.activate()
        return Gdk.EVENT_PROPAGATE

    def key_press_cb(self, controller, keyval, keycode, state):
        if not self.is_active and keyval != Gdk.KEY_backslash:
            return Gdk.EVENT_PROPAGATE
        match keyval:
            case Gdk.KEY_Escape:
                self.popdown()
            case Gdk.KEY_Tab | Gdk.KEY_Return:
                row = self.listbox.get_selected_row()
                row.emit("activate")
                return Gdk.EVENT_STOP
            case _:
                if controller.forward(self.listbox):
                    return Gdk.EVENT_STOP
                else:
                    controller.forward(self.textview)
                    self.listbox.invalidate_filter()
                    self.update_position()
                    idx = 0
                    row = self.listbox.get_row_at_index(idx)
                    while not self.filter_func(row):
                        idx += 1
                        row = self.listbox.get_row_at_index(idx)
                        if row is None:
                            break
                    self.listbox.select_row(row)
                    if row is None:
                        self.popdown()
                    else:
                        row.grab_focus()
                    return Gdk.EVENT_STOP
        return Gdk.EVENT_PROPAGATE

    def key_release_cb(self, controller, keyval, keycode, state):
        if not self.is_active and keyval != Gdk.KEY_backslash:
            return
        controller.forward(self.listbox)

    def activate(self):
        mark = Gtk.TextMark.new("autocomplete", left_gravity=True)
        buffer = self.get_parent().get_buffer()
        it = buffer.get_iter_at_mark(buffer.get_insert())
        buffer.add_mark(mark, it)
        self.listbox.set_filter_func(self.filter_func)
        self.update_position()
        self.popup()
        row = self.listbox.get_row_at_index(0)
        self.listbox.select_row(row)
        row.grab_focus()
        self.is_active = True

    def row_activated_cb(self, listbox, row):
        buffer = self.textview.get_buffer()
        text = self.get_typed_text()
        buffer.insert_at_cursor(row.command.lstrip(text))
        self.popdown()

    def get_typed_text(self):
        buffer = self.textview.get_buffer()
        mark = buffer.get_mark("autocomplete")
        start_it = buffer.get_iter_at_mark(mark)
        end_it = buffer.get_iter_at_mark(buffer.get_insert())
        text = buffer.get_text(start_it, end_it, include_hidden_chars=False)
        return text

    def filter_func(self, row):
        if row is None:
            return False
        text = self.get_typed_text()
        return row.text.find(text) != -1

    def button_release_cb(self, window, n, x, y):
        self.is_active and self.deactivate()

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
