from tornado.escape import json_decode as decode
from tornado.escape import json_encode as encode
import redis
r = redis.Redis()
r.flush()
from models import User, Item, Group
r.keys('*')
User(name='Skylar')
r.keys('*')
u=User(name='Skylar')
u.name
u.id
u.create_item('Create a talk for PyCon 2011')
r.keys('*')
i = Item(1)
i.id
i.name
i.get_creator()
u.created_items()
u2= User(id=i.get_creator())
u2.name
r.keys('*')
u is u2
u == u2
u.create_group('PyCon goers')
g = Group(1)
g.name
u.set_service('google', '{"email":"skylar.saveland@gmail.com"}')
u.get_service('google')['email']
u.del_service('google')
u.get_service('google')
r.keys('*')
u.groups()
u.created_groups()
u.assigned_groups()
u.del_group(1)
u.created_groups()
r.keys('*')
u.create_group('PyCon speakers')
u.created_groups()
r.keys('*')

