from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GObject

class AutocompletePopover(Gtk.Popover):
    __gtype_name__ = 'AutocompletePopover'

    __gsignals__ = {
        'update-position': (GObject.SIGNAL_RUN_FIRST, None, ()),
    }

    def __init__(self, parent):
        super().__init__()
        self.set_parent(parent)

        controller = Gtk.EventControllerKey()
        controller.connect("key_released", self.key_release_cb)
        parent.add_controller(controller)
        self.set_autohide(True)
        self.is_active = False

        #controller = Gtk.GestureClick()
        #controller.connect("released", self.button_release_cb)
        #parent.get_root().add_controller(controller)

        self.listbox = Gtk.ListBox()
        self.set_child(self.listbox)

        # This is an example to fill up the rows in the popover
        row = Gtk.ListBoxRow()
        row.text = "Hello pop 1"
        row.set_child(Gtk.Label.new(row.text))
        self.listbox.append(row)
        row = Gtk.ListBoxRow()
        row.text = "Hello pop 2"
        row.set_child(Gtk.Label.new(row.text))
        self.listbox.append(row)

    def key_release_cb(self, controller, keyval, keycode, state):
        if not self.is_active and keyval != Gdk.KEY_backslash: return
        self.emit("update-position")
        if keyval == Gdk.KEY_backslash:
            self.popup()
            row = self.listbox.get_row_at_index(0)
            self.listbox.select_row(row)
            self.is_active = True
        if keyval == Gdk.KEY_Return:
            row = self.listbox.get_selected_row()
            if not row:
                self.popdown()
                self.is_active = False

        if keyval == Gdk.KEY_Escape:
            self.popdown()
            self.is_active = False

    def button_release_cb(self, window, n, x, y):
        if not self.is_active: return
        self.popdown()


