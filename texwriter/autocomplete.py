from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GObject

class AutocompletePopover(Gtk.Popover):
    __gtype_name__ = 'AutocompletePopover'

    def __init__(self, parent):
        super().__init__()
        self.set_parent(parent)
        self.set_autohide(False)
        self.is_active = False
        self.listbox = Gtk.ListBox()
        self.set_child(self.listbox)

        controller = Gtk.EventControllerKey()
        controller.connect("key_pressed", self.key_press_cb)
        parent.add_controller(controller)

        controller = Gtk.GestureClick()
        controller.connect("released", self.button_release_cb)
        parent.get_root().add_controller(controller)

        # This is an example to fill up the rows in the popover
        row = Gtk.ListBoxRow()
        row.text = "\\alpha"
        row.set_child(Gtk.Label.new(row.text))
        self.listbox.append(row)
        row = Gtk.ListBoxRow()
        row.text = "\\beta"
        row.set_child(Gtk.Label.new(row.text))
        self.listbox.append(row)

    def key_press_cb(self, controller, keyval, keycode, state):
        if not self.is_active and keyval != Gdk.KEY_backslash: return
        match keyval:
            case Gdk.KEY_backslash:
                self.activate()
                return False
            case Gdk.KEY_Escape:
                self.deactivate()
                return True
            case Gdk.KEY_Return:
                row = self.listbox.get_selected_row()
                if not row:
                    self.deactivate()
                return True
            case Gdk.KEY_Down:
                self.select_next_row()
                return True
            case Gdk.KEY_Up:
                self.select_prev_row()
                return True
            case _:
                self.update_position()

    def activate(self):
        self.update_position()
        self.popup()
        row = self.listbox.get_row_at_index(0)
        self.listbox.select_row(row)
        self.is_active = True

    def deactivate(self):
        self.popdown()
        self.is_active = False

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
