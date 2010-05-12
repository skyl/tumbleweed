import os
import tornado.httpserver
import tornado.ioloop
import tornado.web
import tornado.auth
import tornado.escape
from tornado.escape import json_encode as encode
from tornado.escape import json_decode as decode
import tornado.options
from tornado.options import define, options
import uimodules

import redis
r = redis.Redis()

class BaseHandler(tornado.web.RequestHandler):
    '''
    >>> r=tornado.web.RequestHandler
    >>> r.SUPPORTED_METHODS
    ('GET', 'HEAD', 'POST', 'DELETE', 'PUT')
    '''
    def google_json(self):
        c = self.get_secure_cookie('google')
        if c:
            return c
        elif self.name():
            d = r.get('%s%s' % (self.name(), ':google'))
            return d
    def _google(self):
        return decode(self.google_json()) if self.google_json() else None

    def twitter_json(self):
        c = self.get_secure_cookie('twitter')
        if c:
            return c
        elif self.name():
            d = r.get('%s%s' % (self.name(), ':twitter'))
            return d
    def _twitter(self):
        return decode(self.twitter_json()) if self.twitter_json() else None

    def facebook_json(self):
        c = self.get_secure_cookie('facebook')
        if c:
            return c
        elif self.name():
            d = r.get('%s%s' % (self.name(), ':facebook'))
            return d
    def _facebook(self):
        return decode(self.facebook_json()) if self.facebook_json() else None

    def get_current_user(self):
        name = self.get_secure_cookie("user")
        if name in r.smembers('___users'):
            return name
    def name(self):
        return self.get_current_user()

    def fully_authed(self):
        return self._google() and self._twitter() and self._facebook()
    def any_auth(self):
        return self._google() or self._twitter() or self._facebook()

    def common_context(self):
        return { 'name': self.name(), 'google': self._google(),
            'facebook': self._facebook(), 'twitter': self._twitter(),
            'fully_authed': self.fully_authed(), 'any_auth': self.any_auth()
        }

class AuthHandler(BaseHandler):
    '''Maybe there will be common attrs to all Auth Handlers?'''
    pass

class MainHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.render('templates/base.html', **self.common_context())
    def post(self):
        pass

class LogoutHandler(BaseHandler):
    '''logout the user and redirect to login'''
    def get(self):
        self.clear_cookie('user')
        self.clear_cookie('google')
        self.clear_cookie('twitter')
        self.clear_cookie('facebook')
        self.redirect('/login')

class LoginHandler(BaseHandler):
    '''Show the different login options'''
    def get(self):
        if self.get_current_user():
            self.redirect('/')
        if self.fully_authed():
            self.redirect('/create')
        self.render('templates/auth/login.html', **self.common_context())

class CreateHandler(BaseHandler):
    '''We come here with a cookie from somewhere but no User so we get a username and create'''
    def get(self):
        self.render('templates/auth/create.html', **self.common_context())
    def post(self):
        name = self.get_argument('key')
        if name and not name in r.smembers('___users'):
            twitter = self.get_secure_cookie('twitter')
            google = self.get_secure_cookie('google')
            facebook = self.get_secure_cookie('facebook')
            r.sadd('___users', name)
            self.set_secure_cookie("user", name)
            if twitter:
                r.set('%s%s' % (name, ':twitter'), twitter)
                r.set('%s%s' % ('twitter:', self._twitter()['access_token']['user_id']), name)
            if google:
                r.set('%s%s' % (name, ':google'), google)
                r.set('%s%s' % ('google:', self._google()['email']), name)
            if facebook:
                r.set('%s%s' % (name, ':facebook'), facebook)
                r.set('%s%s' % ('facebook:', self._facebook()['uid']), name)
            next = self.get_argument('next')
            if next == '/create':
                self.redirect('/')
            else:
                self.redirect(next)
        else:
            # we need to return forbidden here, can't create a key that exists
            pass

class CheckUserName(tornado.web.RequestHandler):
    def get(self):
        key = self.get_argument('key')
        if r.sismember('___users', key):
            self.write('false')
        else:
            self.write('true')

class GoogleHandler(AuthHandler, tornado.auth.GoogleMixin):
    '''get the form, post and login or create'''
    @tornado.web.asynchronous
    def get(self):
        if self.get_argument("openid.mode", None):
            self.get_authenticated_user(self.async_callback(self._on_auth))
            return
        self.authenticate_redirect()

    def _on_auth(self, google):
        if not google:
            raise tornado.web.HTTPError(500, "Google auth failed")
        google_key = "%s%s" % ('google:', google['email'])
        username = r.get(google_key)
        google_info_key = "%s%s" % (username, ':google')
        if username:
            self.set_secure_cookie("user", username)
            r.set(google_info_key, encode(google))
            self.redirect("/")
        else:
            self.set_secure_cookie("google", tornado.escape.json_encode(google))
            self.redirect("/create")

class TwitterHandler(AuthHandler, tornado.auth.TwitterMixin):
    '''Authenticate with Twitter and save all of the relevant bits'''
    @tornado.web.asynchronous
    def get(self):
        if self.get_argument("oauth_token", None):
            self.get_authenticated_user(self.async_callback(self._on_auth))
            return
        self.authorize_redirect()

    def _on_auth(self, twitter):
        if not twitter:
            raise tornado.web.HTTPError(500, "Twitter auth failed")
        twitter_key = "%s%s" % ('twitter:', twitter['access_token']['user_id'])
        username = r.get(twitter_key) # see if we have a user with that twitter id
        twitter_info_key = "%s%s" % (username, ':twitter')
        if username:
            self.set_secure_cookie("user", username)
            # write the lates information to redis
            r.set(twitter_info_key, encode(twitter))
            self.redirect("/")
        else:
            self.set_secure_cookie("twitter", encode(twitter))
            self.redirect("/create")

class FacebookHandler(AuthHandler, tornado.auth.FacebookMixin):
    '''login with facebook and redirect to `/`'''
    @tornado.web.asynchronous
    def get(self):
        if self.get_argument("session", None):
            self.get_authenticated_user(self.async_callback(self._on_auth))
            return
        self.authenticate_redirect()

    def _on_auth(self, facebook):
        if not facebook:
            raise tornado.web.HTTPError(500, "Facebook auth failed")
        facebook_key = "%s%s" % ('facebook:', facebook['uid'])
        username = r.get(facebook_key)
        facebook_info_key = "%s%s" % (username, ':facebook')
        if username:
            self.set_secure_cookie("user", username)
            r.set(facebook_info_key, encode(facebook))
            self.redirect("/")
        else:
            self.set_secure_cookie("facebook", encode(facebook))
            self.redirect("/create")

urls = [
    (r'/', MainHandler),
    # Authentication urls
    (r'/login', LoginHandler),
    (r'/logout', LogoutHandler),
    (r'/google', GoogleHandler),
    (r'/twitter', TwitterHandler),
    (r'/facebook', FacebookHandler),
    (r'/create', CreateHandler),
    (r'/check-username', CheckUserName),
]

settings = {
    "static_path": os.path.join(os.path.dirname(__file__), "static"),
    "cookie_secret": "61oETzKXQAGaYdkL5gEmGeJJFuYh7EQnp2XdTP1o/Vo=",
    "login_url": "/login",
    "xsrf_cookies": True,
    "ui_modules": uimodules,
    # these credentials are good for localhost:8000
    "twitter_consumer_key": 'f2QpwYkwTdylQCLebkXOIA',
    "twitter_consumer_secret": 'E3DrUDn3GSv1tZetps8Whg6y5p3FPuP70dHQThcJrI',
    "facebook_api_key": 'dbee7c681fb8b3c375c5fc4fedea46e0',
    "facebook_secret": 'b3f2adf023c9af70934c003e1c438d7c',
    "friendfeed_consumer_key": '6e4475caaf5541f3a11a0d434de241e2',
    "friendfeed_consumer_secret": 'b27d620f896947dab92e8ada4f7be18b68528faaff3d48749b9b663335baad42',
}
application = tornado.web.Application(urls, **settings)

# can't get this to work :(
import tornado.autoreload

if __name__ == "__main__":
    #tornado.locale.load_translations(
    #    os.path.join(os.path.dirname(__file__), "translations"))
    http_server = tornado.httpserver.HTTPServer(application)
    http_server.listen(8000)
    t=tornado.ioloop.IOLoop.instance().start()
    #t.autoreload.start()

'''
# appengine wsgi
if __name__ == "__main__":
    application = tornado.wsgi.WSGIApplication([
        (r"/", MainHandler),
    ])
    wsgiref.handlers.CGIHandler().run(application)
'''
