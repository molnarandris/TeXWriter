import re

class LatexParser:

    def __init__(self, buffer):

        buffer.connect("insert-text", self.before_buffer_insert_text)
        buffer.connect_after("insert-text", self.after_buffer_insert_text)

        command_tag = buffer.create_tag("command")
        command_tag.props.foreground = "green"
        comment_tag = buffer.create_tag("comment")
        comment_tag.props.foreground = "gray"
        newline_tag = buffer.create_tag("newline")
        inline_math_tag = buffer.create_tag("inline-math")
        inline_math_tag.props.background = "lightgray"
        newline_tag.props.foreground = "green"

        self.buffer = buffer

    def before_buffer_insert_text(self, buffer, location, text, len):
        buffer.create_mark("insert-start", location, True)

    def after_buffer_insert_text(self, buffer, location, text, len):
        insert_start = buffer.get_mark("insert-start")
        start_it = buffer.get_iter_at_mark(insert_start)
        buffer.delete_mark(insert_start)
        end_it = location
        self.parse(start_it, end_it)

    def parse(self, very_start_it, very_end_it):
        buffer = self.buffer
        it = very_start_it.copy()
        inline_math_start = None
        finished = False
        while not finished:
            match it.get_char():
                case "%":
                    start_it = it.copy()
                    it.forward_to_line_end()
                    buffer.apply_tag_by_name("comment", start_it, it)
                case "\\":
                    start_it = it.copy()
                    it.forward_char()
                    match it.get_char():
                        case "\\":
                            it.forward_char()
                            buffer.apply_tag_by_name("newline", start_it, it)
                        case " ":
                            pass
                        case ch if re.match(r"[A-Za-z]", ch):
                            it.forward_word_end()
                            buffer.apply_tag_by_name("command", start_it, it)
                            it.backward_char()
                        case _:
                            pass
                case "$":
                    end_it = it.copy()
                    end_it.forward_char()
                    if end_it.get_char() != "$":
                        if inline_math_start is not None:
                            it.forward_char()
                            buffer.apply_tag_by_name("inline-math",inline_math_start, it)
                            inline_math_start = None
                        else:
                            inline_math_start = it.copy()
                    else:
                        it.forward_char()
            if not it.forward_char() or not it.in_range(very_start_it, very_end_it):
                finished = True

