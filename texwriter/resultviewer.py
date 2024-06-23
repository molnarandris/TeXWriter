from gi.repository import Gtk

@Gtk.Template(resource_path="/com/github/molnarandris/texwriter/ui/resultviewer.ui")
class ResultViewer(Gtk.Stack):
    __gtype_name__ = 'ResultViewer'

    pdfview = Gtk.Template.Child()
    logview = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

