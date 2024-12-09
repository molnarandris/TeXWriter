import gi
import re
import logging
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import Gio
from gi.repository import Graphene
gi.require_version('Poppler', '0.18')
from gi.repository import Poppler

logger = logging.getLogger("Texwriter")


class PdfViewer(Gtk.ScrolledWindow):
    __gtype_name__ = 'PdfViewer'

    __gsignals__ = {
        'synctex-back': (GObject.SIGNAL_RUN_FIRST, None, (int, str, str)),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.box = Gtk.Box()
        self.box.set_halign(Gtk.Align.CENTER)
        self.box.set_orientation(Gtk.Orientation.VERTICAL)
        self.box.set_spacing(20)
        self.box.set_margin_start(20)
        self.box.set_margin_end(20)
        self.box.set_margin_top(10)
        self.box.set_margin_bottom(10)
        self.set_child(self.box)

        self._scale = 1
        self.file = None
        self.cancellable = None

        controller = Gtk.EventControllerScroll()
        controller.connect("scroll", self.on_scroll)
        controller.set_propagation_phase(Gtk.PropagationPhase.BUBBLE)
        controller.set_flags(Gtk.EventControllerScrollFlags.VERTICAL)
        self.box.add_controller(controller)

    @GObject.Property(type=float)
    def scale(self):
        "Scaling of the PDF"
        return self._scale

    @scale.setter
    def scale(self, value):
        self._scale = value
        for child in self.box:
            child.get_child().set_scale(value)

    def load_file(self, file):
        child = self.box.get_first_child()
        while child is not None:
            self.box.remove(child)
            page = child.get_child()
            page.unparent()
            del page.poppler_page
            del page
            child.set_child(None)
            del child
            child = self.box.get_first_child()
        try:
            poppler_doc = Poppler.Document.new_from_gfile(file, None, None)
            self.file = file
            for i in range(poppler_doc.get_n_pages()):
                page = PdfPage(poppler_doc.get_page(i), self.scale)
                page.connect("synctex-back", self.on_synctex_back)
                overlay = Gtk.Overlay()
                overlay.set_child(page)
                self.box.append(overlay)
            del poppler_doc
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
        hadj.set_upper(hadj.get_upper()*scaling)
        vadj.set_upper(vadj.get_upper()*scaling)
        hadj.set_value(h*scaling)
        vadj.set_value(v*scaling)
        self.scale *= scaling
        return Gdk.EVENT_STOP

    def synctex_fwd(self, rects):
        for r in rects:
            w,h,x,y,p = r
            rect = SynctexRect(w,h,x,y, self.scale)
            page = self.get_page(p)
            page.add_overlay(rect)

        _, _, _, y, p = r
        self.scroll_to(p, y)

    def on_synctex_back(self, page, x, y, around, after):
        if self.file is None: return
        arg = str(page.page_number) + ":" + str(x) + ":" + str(y)
        arg += ":" + self.file.get_path()
        cmd = ['flatpak-spawn', '--host', 'synctex', 'edit', '-o', arg]
        flags = Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE
        proc = Gio.Subprocess.new(cmd, flags)
        if self.cancellable:
            self.cancellable.cancel()
        self.cancellable = Gio.Cancellable()
        proc.communicate_utf8_async(None, None, self.synctex_back_complete,
                                    around, after)

    def synctex_back_complete(self, source, result, around, after):
        logger.info("Synctex back complete")
        success, stdout, _ = source.communicate_utf8_finish(result)
        self.cancellable = None
        if stdout is not None:
            result = re.search("Line:(.*)", stdout)
            line = int(result.group(1)) - 1
            self.emit("synctex-back", line, around, after)
        else:
            logger.warning("Synctex back failed")

    def get_page(self, n):
        child = self.box.get_first_child()
        for i in range(n):
            child = child.get_next_sibling()
        return child

    def scroll_to(self, page_num, y):
        page = self.get_page(page_num).get_child()
        point = Graphene.Point()
        point.init(0, y)
        _, p = page.compute_point(self.box, point)
        viewport = self.box.get_parent()
        vadj = viewport.get_vadjustment()
        vadj.set_value(p.y-vadj.get_page_size()*0.302)


class PdfPage(Gtk.Widget):
    __gtype_name__ = 'PdfPage'

    __gsignals__ = {
        'synctex-back': (GObject.SIGNAL_RUN_FIRST, None,
                         (float, float, str, str)),
    }

    def __init__(self, poppler_page, scale=1.0):
        super().__init__()
        self.set_halign(Gtk.Align.FILL)
        self.set_valign(Gtk.Align.CENTER)
        self.poppler_page = poppler_page
        self.bg_color = Gdk.RGBA()
        self.bg_color.parse("white")
        self.set_scale(scale)
        controller = Gtk.GestureClick()
        controller.set_propagation_phase(Gtk.PropagationPhase.BUBBLE)
        controller.connect("released", self.on_click)
        self.add_controller(controller)

    @property
    def page_number(self):
        return self.poppler_page.get_index()+1

    def on_click(self, controller, n_press, x, y):
        x = x/self.scale
        y = y/self.scale
        if n_press != 2:
            return

        # Retrieve all text from page and locate the cursor in one of them
        _, rectangles = self.poppler_page.get_text_layout()
        ind = 0
        for rect in rectangles:
            if rect.y1 > y or (rect.y2 >= y and rect.x1 > x):
                break
            ind += 1
        if ind > 0:
            ind = ind-1

        # Try to get the text around it
        rect = Poppler.Rectangle()
        rect.x1 = min(rectangles[ind-10].x1, rectangles[ind].x1)
        rect.x2 = max(rectangles[ind+10].x2, rectangles[ind].x2)
        rect.y1 = rectangles[ind].y1
        rect.y2 = rectangles[ind].y2
        text_around = self.poppler_page.get_text_for_area(rect)
        rect.x1 = rectangles[ind].x1
        text_after = self.poppler_page.get_text_for_area(rect)
        self.emit("synctex-back", x, y, text_around, text_after)

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

    def __init__(self, width, height, x, y, scale):
        super().__init__()
        height += 2
        self.color = Gdk.RGBA()
        self.color.parse("#FFF38060")
        self.set_halign(Gtk.Align.START)
        self.set_valign(Gtk.Align.START)
        self.set_margin_top((y-height+1)*scale)
        self.set_margin_start(x*scale)
        GLib.timeout_add(700, self.do_destroy)
        self.set_size_request(width*scale, height*scale)

    def do_snapshot(self, snapshot):
        rect = Graphene.Rect().init(0, 0, self.get_width(), self.get_height())
        snapshot.append_color(self.color, rect)

    def do_destroy(self):
        self.unparent()
        return False
