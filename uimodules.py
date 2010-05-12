import tornado.web

class Task(tornado.web.UIModule):
    def render(self, task):
        return self.render_string(
            "templates/module-entry.html", show_comments=show_comments)

