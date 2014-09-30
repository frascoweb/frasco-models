

class ModelNotFoundError(Exception):
    pass


class Backend(object):
    def __init__(self, app, options):
        pass

    def connect(self):
        pass

    def close(self):
        pass

    def ensure_model(self, model_name):
        pass

    def ensure_fields(self, model_name, fields):
        pass

    def find(self, pk):
        pass

    def find_all(self, query):
        pass

    def find_first(self, query):
        pass

    def find_one(self, query):
        pass

    def count(self, query):
        pass

    def save(self, obj):
        pass

    def delete(self, obj):
        pass
