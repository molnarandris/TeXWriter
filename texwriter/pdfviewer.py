import gi
import logging
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import Graphene
gi.require_version('Poppler', '0.18')
from gi.repository import Poppler

logger = logging.getLogger("Texwriter")


class PdfViewer(Gtk.ScrolledWindow):
    __gtype_name__ = 'PdfViewer'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.box = Gtk.Box()
        self.box.set_orientation(Gtk.Orientation.VERTICAL)
        self.box.set_spacing(20)
        self.box.set_margin_start(20)
        self.box.set_margin_end(20)
        self.box.set_margin_top(10)
        self.box.set_margin_bottom(10)
        self.set_child(self.box)

        self.scale = 1

        controller = Gtk.EventControllerScroll()
        controller.connect("scroll", self.on_scroll)
        controller.set_propagation_phase(Gtk.PropagationPhase.BUBBLE)
        controller.set_flags(Gtk.EventControllerScrollFlags.VERTICAL)
        self.box.add_controller(controller)

    def load_file(self, file):
        child = self.box.get_first_child()
        while child:
            self.box.remove(child)
            child = self.box.get_first_child()
        try:
            poppler_doc = Poppler.Document.new_from_gfile(file, None, None)
            for i in range(poppler_doc.get_n_pages()):
                page = PdfPage(poppler_doc.get_page(i))
                overlay = Gtk.Overlay()
                overlay.set_child(page)
                self.box.append(overlay)
        except:
            logger.warning(f"Opening the following pdf failed: {file.get_path()}")

    def on_scroll(self, controller, dx, dy):
        if not controller.get_current_event_state() == Gdk.ModifierType.CONTROL_MASK:
            return Gdk.EVENT_PROPAGATE
        viewport = self.box.get_parent()
        hadj = viewport.get_hadjustment()
        vadj = viewport.get_vadjustment()
        h = hadj.get_value()
        v = vadj.get_value()
        scaling = 1.02 if dy > 0 else 1.0/1.02
        self.scale *= scaling
        hadj.set_upper(hadj.get_upper()*scaling)
        vadj.set_upper(vadj.get_upper()*scaling)
        hadj.set_value(h*scaling)
        vadj.set_value(v*scaling)
        for child in self.box:
            child.get_child().set_scale(self.scale)
        return Gdk.EVENT_STOP

    def synctex_fwd(self, width, height, x, y, page):
        rect = SynctexRect(width, height, x, y, self.scale)
        overlay = self.get_page(page)
        overlay.add_overlay(rect)
        self.scroll_to(page,y)

    def get_page(self, n):
        child = self.box.get_first_child()
        for i in range(n):
            child = child.get_next_sibling()
        return child

    def scroll_to(self, page_num, y):
        page = self.get_page(page_num).get_child()
        point = Graphene.Point()
        point.init(0,y)
        _, p = page.compute_point(self.box, point)
        viewport = self.box.get_parent()
        vadj = viewport.get_vadjustment()
        vadj.set_value(p.y-vadj.get_page_size()*0.302)

class PdfPage(Gtk.Widget):
    __gtype_name__ = 'PdfPage'

    def __init__(self, poppler_page):
        super().__init__()
        self.set_halign(Gtk.Align.FILL)
        self.set_valign(Gtk.Align.CENTER)
        self.poppler_page = poppler_page
        self.scale = 1
        self.bg_color = Gdk.RGBA()
        self.bg_color.parse("white")
        self.set_size_request(*poppler_page.get_size())

    """"
    def do_measure(self, orientation, for_size):
        Implementation of the measure vfunc for gtk widget.
        I did not overwrite the get_request_mode vfunc, so this widget is
        constant size: for_size = -1 in all calls of this function.

        The widget should be a scaling of the poppler page.

        width, height = self.poppler_page.get_size()
        if orientation == Gtk.Orientation.HORIZONTAL:
            size = width * self.scale
        else:
            size = height * self.scale
        return (size, size, -1, -1)
    """

    def set_scale(self, scale):
        width, height = self.poppler_page.get_size()
        self.scale = scale
        self.set_size_request(scale*width, scale*height)

    def do_snapshot(self, snapshot):
        """ This virtual function manages the display of the widget.
        """
        pw, ph = self.poppler_page.get_size()
        rect = Graphene.Rect().init(0, 0, self.scale*pw, self.scale*ph)
        snapshot.append_color(self.bg_color, rect)
        ctx = snapshot.append_cairo(rect)
        ctx.scale(self.scale, self.scale)
        self.poppler_page.render(ctx)


class SynctexRect(Gtk.Widget):
    __gtype_name__ = 'SynctexRect'

    def __init__(self, width, height, x,y,scale):
        super().__init__()
        height += 15
        self.color = Gdk.RGBA()
        self.color.parse("#FFF38080")
        self.set_halign(Gtk.Align.START)
        self.set_valign(Gtk.Align.START)
        self.set_margin_top((y-height/2)*scale)
        self.set_margin_start(x*scale)
        GLib.timeout_add(700, self.do_destroy)
        self.set_size_request(width*scale, height*scale)

    def do_snapshot(self, snapshot):
        rect = Graphene.Rect().init(0, 0, self.get_width(), self.get_height())
        snapshot.append_color(self.color, rect)

    def do_destroy(self):
        self.unparent()
        return False

