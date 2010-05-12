'''
keys:

::site-wide keys::
'users'
    The set of usernames.
    r.sismember('users', 'foouser')
'users_ids'
    The set of user_id s
'users_incr'
    The next user number
'groups'
    List of all groups
'groups_incr'
    The next group number
'items'
    List of all item ids
'items_incr'
    The next item number

::get username from service::
'services:<service>:<unique_id>'
    Value is our username for the service and unique identifier.

::user data::
'users:<username>'
    returns the user id from the user name
'users:<id>'
    returns the username given the id

'users:<user_id>:<service>'
    Value is the the json information associated with the username and the service.
'users:<user_id>:set:created_items'
    Set of item ids created by the user
'users:<user_id>:set:assigned_items'
    Set of item ids assigned to the user
'users:<user_id>:set:created_groups'
    The set of group ids created by the user.
'users:<user_id>:set:assigned_groups'
    The set of group ids that the user has permission to
'users:<id>:updates'
    List of update ids for the user

::groups and items::
'groups:<id>'
    json dict of group attributes
'groups:<id>:creator'
    username of the creator/leader (can change?)
'groups:<id>:members'
    Set of users who have permission with this group
'groups:<id>:items'
    List of item ids for the group

'items:<id>'
    json dict of item attributes
'items:<id>:creator'
    the id of the creator
'items:<id>:group'
    the id of the group that the item belongs to
'items:<id>:members'
    set of usernames for watchers/privileged

::updates::
'update:<update_id>'
    Returns the update string

'''
#from IPython.Shell import IPShellEmbed
#ipython = IPShellEmbed()

import re
from tornado.escape import json_decode as decode
from tornado.escape import json_encode as encode
import redis
r = redis.Redis()

# Somehow we can abstract what is in these models
# through metaclass or inheritance TODO
class ModelBase(type):

    # This anti-idiom is a placeholder :P
    pass

class Model(object):
    __metaclass__ = ModelBase

    def __eq__(self, other):
        return self.id == other.id and isinstance(other, self.__class__)

# perhaps we can have a base manager like django that can be a class
# thus we get User.objects.all() or some such TODO
class BaseManager(object):
    pass

class User(Model):

    _pk = 'users_incr'
    _id = 'users:id_for:%s' # given name get id
    _name = 'users:name_for:%s' # given id get name
    _service = 'users:{id}:{service}' # id and service get info
    _created_items = 'users:%s:set:created_items' #items set
    _assigned_items = 'users:%s:set:assigned_items'
    _created_groups = 'users:%s:set:created_groups'
    _assigned_groups = 'users:%s:set:assigned_groups'
    _updates = 'users:%s:updates'

    _update_str = 'updates:%s'

    def __init__(self, id=None, name=''):
        '''pass in a name or id and we will try to retrieve (or create with name)

        Name can not have spaces'''
        if re.search(r'\s', name): # no spaces allowed
            raise Exception('Name can not have spaces')
        if id:
            name = r.get(self._name % id)
            if not name:
                raise Exception('There is no user with that id, use kwargs perhaps')
        elif name:
            id = r.get(self._id % name.lower())
            if id:
                db_name = r.get(self._name % id)
                if db_name:
                    name=db_name
        if not id and name:
            id = r.incr(self._pk)
            r.set(self._name % id, name)
            r.set(self._id % name.lower(), id)
        self.id = id
        self.name = name

        self.rname = self._name % self.id
        self.rcreated_items = self._created_items % self.id
        self.rassigned_items = self._assigned_items % self.id
        self.rcreated_groups = self._created_groups % self.id
        self.rassigned_groups = self._assigned_groups % self.id
        self.rupdates = self._updates % self.id

    # service read
    def get_service(self, service):
        '''Returns the dict associated with the user for a given service'''
        rservice = self._service.format(id=self.id, service=service)
        json = r.get(rservice) # convenient but not atomic
        if json:
            return decode(json)
        else: return None
    # service C/U
    def set_service(self, service, json):
        '''Given json string, we set this information to 'users:<id>:<service>' key'''
        rservice = self._service.format(id=self.id, service=service)
        return r.set(rservice, json)
    # service D
    def del_service(self, service):
        '''Delete the key and value for this user/service'''
        rservice = self._service.format(id=self.id, service=service)
        return r.delete(rservice)

    def create_group(self, json_string):
        '''Get new id, create the group with the value (name or json)'''
        g = Group(name=json_string)
        g.set_creator(self.id)
        r.sadd(self.rcreated_groups, g.id)
        return g.id

    def created_groups(self):
        '''Returns set of created groups'''
        return r.smembers(self.rcreated_groups)
    def assigned_groups(self):
        '''Returns set of assigned groups'''
        return r.smembers(self.rassigned_groups)
    def groups(self):
        '''Returns set of created groups (ids)'''
        return r.sunion(self.rcreated_groups, self.rassigned_groups)

    def add_to_group(self, group_id):
        r.sadd('groups:%s:members' % group_id, self.id)
        return r.sadd(self.rassigned_groups, self.id)

    def del_group(self, id, cascade=True):
        if r.sismember(self.rcreated_groups, id):
            r.delete('groups:%s' % id)
            r.srem(self.rcreated_groups, id)
            if cascade: # need to test this and think it through TODO
                [ r.delete(k) for k in r.keys('groups:%s:*' % id ) ]
                #[ r.delete(k) for k in r.keys('items:

    def set_attribute_to_group(self, id, key, value):
        if id in self.groups():
            return r.set('groups:%s:attr:%s' % (id, key), value)
        else:
            raise Exception('This is not one of your groups if it exists')

    def create_item(self, item_name):
        '''Add an item to the created set'''
        i = Item(name=item_name, creator=self.id)
        r.sadd(self.rcreated_items, i.id)
        return i.id

    def created_items(self):
        '''Ids for items created by the user'''
        return r.smembers(self.rcreated_items)
    def assigned_items(self):
        '''Set of ids for items assigned to the user'''
        return r.smembers(self.rassigned_items)
    def items(self):
        '''Union of created and assigned'''
        return r.sunion(self.rcreated_items, self.rassigned_items)

    def assign_item(self, item_id):
        '''Add the item_id to our assigned items set'''
        return r.sadd(self.rassigned_items, item_id)
    def unclaim_item(self, item_id):
        return r.srem(self.rassigned_items, item_id)

    def destroy_item(self, item_id):
        if r.sismember(self.rcreated_items, item_id):
            return s.srem(self.rassigned_items, item_id)

    def update_ids(self, n=None):
        '''List of updates for the user, limit to 'n' if provided'''
        if not n:
            return r.lrange(self.rupdates, 0, -1)
        else:
            return r.lrange(self.rupdates, 0, n+1)
    def add_update(self, message):
        '''Create the update and add to the users updates'''
        update_id = r.incr('updates_incr')
        r.set('updates:%s' % update_id, message)
        return r.push(self.rupdates, update_id, head=True)
    def del_update(self, id):
        '''Delete the update from the user and the global updates'''
        if id in self.rupdates():
            r.lrem(self.rupdates, id)
            return r.delete('updates:%s' % id)
        else:
            raise Exception('This is not the User\'s update if it exists')
    def update_texts(self, n=None):
        ids = self.update_ids(n=n)
        return [ r.get('updates:%s' % i) for i in ids ]


class Item(Model):
    _pk = 'items_incr'
    _name = 'items:%s' # give id, get name
    # named attrs
    _creator = 'items:%s:fk:creator' # get user_id of the creator (str)
    _group = 'items:%s:fk:group' # id of the group (str)
    _members = 'items:%s:mm:members' # set of member ids
    _comments = 'items:%s:list:comments' # comment_ids --REVERSE fk?
    _components = 'items:%s:sset:components' # score is priority perhaps, just score/string
    # generic keyspaces
    _attrs = 'items:%s:str:attrs:' # base key for any number of string attributes
    _lattrs = 'items:%s:set:attrs:' # base key for any number of list attributes
    _sattrs = 'items:%s:list:attrs:' # base key for any number of set attributes
    _ssattrs = 'items:%s:sset:attrs:' # base key for any number of sorted set attributes

    def __init__(self, id=None, name=None, creator=None, group=None): #, owner_id=None, group=None, members=None):
        '''if instantiated with an id, then we retrieve, else we create

        name will not be in a key so it can have spaces even in redis 1.1'''
        if id:
            # if id and name are given, well, id wins
            name = r.get(self._name % id)
            if not name:
                raise Exception('Item does not exist')
        if not id and name:
            # name is not unique so we won't fetch by that
            id = r.incr(self._pk)
            r.set(self._name % id, name)
        self.id = id
        self.name = name
        self.rcreator = self._creator % self.id
        if creator:
            r.set(self.rcreator, creator)
        self.rgroup = self._group % self.id
        if group:
            r.set(self.rgroup, group)
        self.rmembers = self._members % self.id
        self.rcomments = self._comments % self.id
        self.rcomponents = self._components % self.id
        # generic
        # certainly we can move these out into parent of metaclass?
        self.attrs = self._attrs % self.id
        self.lattrs = self._lattrs % self.id
        self.sattrs = self._sattrs % self.id
        self.ssattrs = self._ssattrs % self.id

    def get_creator(self):
        return r.get(self.rcreator)
    def set_creator(self, user_id):
        if not r.sismember('user_ids', user_id):
            raise Exception('User does not exist')
        return r.set(self.rcreator, user_id)

    def get_group(self):
        '''Returns the id of the group that owns the Item'''
        return r.get(self.rgroup)
    def set_group(self, group_id):
        '''Assigns this item to the group'''
        return r.set(self.rgroup, group_id)
        # We should add the group items set/list?

    def get_members(self):
        return r.smembers(self.rmembers)
    def add_member(self, user_id):
        return r.sadd(self.rmembers, user_id)
    def rm_member(self, user_id):
        return r.srem(self.rmembers, user_id)
    def user_is_member(self, user_id):
        return user_id in self.members()

    def add_comment(self, comment_id, head=False):
        return r.push(self.rcomments, comment_id, head=head)
    def get_comments(self, num=-1):
        return r.lrange(self.rcomments, 0, num)
    def rm_comment(self, comment_id, num=0):
        '''Delete all comments of the given id'''
        return r.lrem(self.rcomments, comment_id, num=num)

    def add_component(self, json):
        '''json can just be text for name'''
        return r.zadd(self.rcomponents, json, 1)
    def rm_component(self, json):
        return r.zrem(self.rcomponents, json)
    def components(self, start=0, end=-1, desc=True):
        return r.zrange(self, start, end, desc)
    def components_by_score(self, min, max):
        return r.zrangebyscore(self.rcomponents, min, max)
    def component_score_tuples(self, start=0, end=-1, desc=True):
        s = self.rcomponents
        zip(
            [r.zscore(s, m) for m in r.zrange(s, 0, -1, desc=desc)],
            r.zrange(s, 0, -1, desc=desc)
        )
    def num_components(self):
        return r.zcard(self.rcomponents)

    def set_string_attr(self, key, value):
        return r.set(self.attrs + key, value)
    def getset_string_attr(self, key, value):
        return r.getset(self.attrs + key, value)
    def get_string_attr(self, key):
        return r.get(self.attrs + key)

    # maybe we will do all of the methods for the types but,
    # for now, let's just return the redis keys for manual manipulation.
    def list_key(self, key):
        return self.lattrs + key
    def set_key(self, key):
        return self.sattrs + key
    def sset_key(self, key):
        return self.ssattrs + key

class Group(Model):
    _pk = 'groups_incr'
    _name = 'groups:%s' # maybe we should call this 'root' or something?
    _creator = 'groups:%s:creator'
    _members = 'groups:%s:members'
    _items = 'groups:%s:list:items'
    _attrs = 'groups:%s:attrs:' # maybe we don't need a separate keyspace for each type

    def __init__(self, id=None, name=None):
        '''pass an id and we will try to fetch the group. Pass a name and we will create.

        name (json string if you prefer) does not need to be unique and we will not retrieve based
        on this string.'''
        if not (id or name):
            raise Exception('pass an id or a name(json if you want)')
        if id:
            name = r.get(self._name % id)
            if not name:
                raise Exception('group does not exist')
        if not id and name:
            id = r.incr(self._pk)
            r.set(self._name % id, name)
        self.id = id
        self.name = name
        self.rname = self._name % id
        self.rcreator = self._creator % id
        self.rmembers = self._members % id
        self.ritems = self._items % id
        self.rattrs = self._attrs % id

    #info CRUD
    def get_name(self):
        '''Returns the dictionary of keys/values for this Group'''
        return decode(r.get(self.rinfo))
    def set_name(self, **kwargs):
        '''Takes a kwargs and updates the group information with them'''
        return r.set(self.rname, encode(kwargs))

    def get_items(self):
        '''Returns the list of items for this Group'''
        return r.lrange(self.ritems, 0, -1)
    def add_item(self, item_id, head=True):
        '''Add and item to the top of the list '''
        return r.push(self.ritems, item_id, head=head)
    def rm_item(self, item_id):
        '''Remove the item by item_id'''
        r.lrem(self.ritems, item_id)
    def get_item(self, index):
        '''Return the item by the index of group-list:items list'''
        return r.lindex(self.ritems, index)

    def members(self):
        '''Returns the set of members for this Group'''
        return r.smembers(self.rmembers)
    def add_member(self, user_id):
        '''Adds a member to the set'''
        return r.sadd(self.rmembers, user_id)
    def rm_member(self, user_id):
        return r.srem(self.rmembers, user_id)

    def get_creator(self):
        '''Returns the username of the leader'''
        return r.get(self.rcreator)
    def set_creator(self, user_id):
        return r.set(self.rcreator, user_id)

    def get_attr(self, key):
        return r.get(self.rattrs + key)

    def set_attr(self, key, value):
        '''Concatentate to the base keyspace (for this object's attributes) the passed key

        and set the value of the computed key to ``value``'''
        return r.set(self.rattrs + key, value)

class Update(Model):
    pass

class DoesNotExistException(Exception):
    pass
