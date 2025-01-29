from gi.repository import Gtk

class LatexBuffer(Gtk.TextBuffer):

    def __init__(self):
        super().__init__()

        command_tag = self.create_tag("command")
        command_tag.props.foreground = "green"
        comment_tag = self.create_tag("comment")
        comment_tag.props.foreground = "gray"
        newline_tag = self.create_tag("newline")
        inline_math_tag = self.create_tag("inline-math")
        inline_math_tag.props.background = "lightgray"
        newline_tag.props.foreground = "green"
        
