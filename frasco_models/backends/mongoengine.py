from __future__ import absolute_import
from frasco_models import Backend, ModelSchemaError, and_
from mongoengine import connect, Document, DynamicDocument
from ..utils import clean_proxy


class MongoengineBackend(Backend):
    name = "mongoengine"

    def __init__(self, app, options):
        super(Backend, self).__init__(app, options)
        connect(self.client[options["db"]],
            host=options.get('host', 'localhost'),
            port=options.get('port', 27017),
            username=options.get('username'),
            password=options.get('password'),
            **options.get('mongo_connect_extra', {}))

    def make_model_base(self):
        return self.make_registering_model_base(Document)

    def ensure_schema(self, name, fields):
        model = self.models[name]
        if isinstance(model, DynamicDocument):
            return
        for fname, _ in fields.iteritems():
            if fname not in model._fields:
                raise ModelSchemaError("Missing field '%s' in model '%s'" % (fname, name))

    def find_by_id(self, model, id):
        if not isinstance(id, ObjectId):
            id = ObjectId(id)
        return model.objects.get(_id=id)

    def find_all(self, query):
        return self._transform_query(query).all()

    def find_first(self, query):
        return self._transform_query(query).first()

    def find_one(self, query):
        return self._transform_query(query).first()

    def count(self, query):
        return self._transform_query(query).count()

    def update(self, query, data):
        return self._transform_query(query).update(**self._prepare_data(data))

    def delete(self, query):
        return self._transform_query(query).delete()

    def _transform_query(self, q):
        qs = q.model.objects
        if q._filters:
            qs = qs.filter(self._transform_query_filter_group(and_(*q._filters)))
        if q._order_by:
            qs = qs.order_by(*[''.join(('+' if v == "ASC" else '-', k)) for k, v in q._order_by])
        if q._offset:
            qs = qs.skip(q._offset)
        if q._limit:
            qs = qs.limit(q._limit)
        return qs

    def _transform_query_filter_group(self, group):
        operator, filters = group.popitem()
        qs = None
        for filter in filters:
            if isinstance(filter, dict):
                q = self._transform_query_filter_group(filter)
                if q is None:
                    continue
            else:
                q = self._transform_query_filter(filter)
            if qs is None:
                qs = q
            elif operator == 'OR':
                qs = qs | q
            else:
                qs = qs & q

        return qs

    def _transform_query_filter(self, filter):
        field, value, operator = filter
        value = clean_proxy(value)
        if field == '_id' and not isinstance(value, ObjectId):
            value = ObjectId(value)
        if operator not in ('eq', 'contains'):
            field = '%s__%s' % (field, operator)
        return Q(**dict([(field, value)]))

    def _prepare_data(self, data):
        out = {}
        for field, value in data.iteritems():
            field, operator = split_field_operator(field)
            if operator == 'incr':
                out['inc__%s' % field] = value
            elif operator == 'push':
                out['push__%s' % field] = value
            else:
                out[field] = value
        return out