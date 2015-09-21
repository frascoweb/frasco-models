from .query import NoResultError
from frasco import AttrDict


class ModelNotFoundError(Exception):
    pass


class ModelSchemaError(Exception):
    pass


class RegisteringMetaClass(type):
    def __init__(cls, name, bases, attrs):
        type.__init__(cls, name, bases, attrs)
        cls.__backend__.models[name] = cls


def ref(model_name=None):
    return {"$ref": model_name}


class Backend(object):
    requires_commit = False

    def __init__(self, app, options):
        self.app = app
        self.options = options
        self.models = {}
        self._db = None

    @property
    def db(self):
        if not self._db:
            self._db = AttrDict(Model=self.make_model_base())
        return self._db

    @db.setter
    def db(self, db):
        self._db = db

    def make_model_base(self):
        return self.make_registering_model_base(object)

    def make_registering_model_base(self, base, name='Model'):
        return RegisteringMetaClass(name, (base,), {"__backend__": self})

    def connect(self):
        pass

    def close(self):
        pass

    def begin_transaction(self):
        pass

    def commit_transaction(self):
        pass

    def rollback_transaction(self):
        pass

    def add(self, obj):
        obj.save()

    def remove(self, obj):
        obj.delete()

    def ensure_model(self, model_name):
        if model_name not in self.models:
            raise ModelNotFoundError('Model %s does not exist' % model_name)
        return self.models[model_name]

    def ensure_schema(self, model_name, fields):
        pass

    def inspect_fields(self, obj):
        fields = []
        for f in dir(obj):
            if not f.startswith('_'):
                fields.append((f, dict(type=None)))
        return fields

    def find_by_id(self, id):
        raise NotImplementedError()

    def find_all(self, query):
        raise NotImplementedError()

    def find_first(self, query):
        raise NotImplementedError()

    def find_one(self, query):
        obj = self.find_first(query)
        if not obj:
            raise NoResultError()
        return obj

    def count(self, query):
        raise NotImplementedError()

    def update(self, query, data):
        raise NotImplementedError()

    def delete(self, query):
        raise NotImplementedError()