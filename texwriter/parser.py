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

        self.in_comment = False
        self.in_command = False
        self.in_inline_math = False
        self.at_command_end = False

    def before_buffer_insert_text(self, buffer, location, text, len):
        buffer.create_mark("insert-start", location, True)

        self.in_command = False
        self.in_inline_math = False
        self.in_comment = False
        self.at_command_end = False

        on_tags = location.get_toggled_tags(toggled_on=True)
        off_tags = location.get_toggled_tags(toggled_on=False)
        in_tags =  [t for t in location.get_tags() if t not in on_tags]

        for tag in in_tags:
            match tag.props.name:
                case "command":
                    self.in_command = True
                case "inline_math":
                    self.in_inline_math = True
                case "comment":
                    self.in_comment = True

        for tag in off_tags:
            if tag.props.name == "command":
                self.at_command_end = True

    def after_buffer_insert_text(self, buffer, location, text, len):
        insert_start = buffer.get_mark("insert-start")
        start_it = buffer.get_iter_at_mark(insert_start)
        buffer.delete_mark(insert_start)
        end_it = location
        self.parse(start_it, end_it)

    def parse_comment(self, it):
        comment_start = it.copy()
        it.forward_to_line_end()
        # handle tags in comment, tags overlapping with comment
        it.forward_char()
        self.buffer.apply_tag_by_name("comment", comment_start, it)
        it.backward_char()

    def parse(self, it, bound):
        # If we are in a tag at the beginning, we don't do anything normally, but might have to break out.
        # If we are at the end of a command/comment tag at the beginning, we have to apply that tag.
        # Otherwise read characters one-by-one...
        buffer = self.buffer
        if self.at_command_end:
            if re.match(r"[A-Za-z]", it.get_char()):
                command_start = it.copy()
                it.forward_word_end()
                self.buffer.apply_tag_by_name("command", command_start, it)
            else:
                self.at_command_end = False
        finished = (it.compare(bound) >= 0)
        inline_math_start = None
        while not finished:
            match it.get_char():
                case "%":
                    self.parse_comment(it)
                case "\\":
                    command_start = it.copy()
                    it.forward_char()
                    if it.compare(bound) >= 0:
                        self.buffer.apply_tag_by_name("command", command_start, it)
                        self.at_command_end = True
                        return
                    match it.get_char():
                        case "\\":
                            it.forward_char()
                            self.buffer.apply_tag_by_name("newline", command_start, it)
                        case " ":
                            self.buffer.apply_tag_by_name("command", command_start, it)
                        case ch if re.match(r"[A-Za-z]", ch):
                            it.forward_word_end()
                            self.buffer.apply_tag_by_name("command", command_start, it)
                            it.backward_char()
                        case _:
                            pass
                case "$":
                    peek = it.copy()
                    peek.forward_char()
                    if peek.get_char() != "$":
                        if inline_math_start is not None:
                            it.forward_char()
                            buffer.apply_tag_by_name("inline-math",inline_math_start, it)
                            inline_math_start = None
                        else:
                            inline_math_start = it.copy()
                    else:
                        it.forward_char()
            if not it.forward_char() or it.compare(bound) >= 0:
                finished = True

