from __future__ import absolute_import
from frasco_models import Backend, and_, split_field_operator, QueryError
from persistpy import *
from ..utils import clean_proxy


class PersistpyBackend(Backend):
    name = "persistpy"

    def __init__(self, app, options):
        super(PersistpyBackend, self).__init__(app, options)
        self.client = MongoClient(options.get("url", "localhost"))
        self.session = Session(self.client[options["db"]])

    def make_model_base(self):
        return self.session.create_model_base()

    def ensure_model(self, name):
        return self.session.mapper.ensure_model(name)

    def ensure_schema(self, name, fields):
        model = self.session.mapper.ensure_model(name)
        for name, spec in fields.iteritems():
            type = spec.pop("type", None)
            if type in (list, dict) and "default" not in spec:
                spec["default"] = type
            model.ensure(**dict([(name, Field(**spec))]))

    def find_by_id(self, model, id):
        return model.query.get(id)

    def find_all(self, query):
        return self._transform_query(query).all()

    def find_first(self, query):
        return self._transform_query(query).first()

    def find_one(self, query):
        return self._transform_query(query).first()

    def count(self, query):
        return self._transform_query(query).count()

    def update(self, query, data):
        return self._transform_query(query).update(self._prepare_data(data))

    def delete(self, query):
        return self._transform_query(query).delete()

    def _transform_query(self, q):
        pq = q.model.query
        if q._filters:
            pq._spec = self._transform_query_filter_group(and_(*q._filters))
        if q._order_by:
            pq._sort = [(k, 1 if v == "ASC" else -1) for k, v in q._order_by]
        if q._offset:
            pq._skip = q._offset
        if q._limit:
            pq._limit = q._limit
        return pq

    def _transform_query_filter_group(self, group):
        operator, filters = group.popitem()
        conditions = []
        for filter in filters:
            if isinstance(filter, dict):
                conditions.append(self._transform_query_filter_group(filter))
            else:
                conditions.append(self._transform_query_filter(filter))
        return dict([(operator, conditions)])

    def _transform_query_filter(self, filter):
        field, value = filter
        field, operator = split_field_operator(field)
        value = clean_proxy(value)
        if field == 'id':
            field = '_id'
        if field == '_id' and not isinstance(value, ObjectId):
            value = ObjectId(value)
        if operator not in ('eq', 'contains'):
            value = dict([("$%s" % operator, value)])
        return dict([(field, value)])

    def _prepare_data(self, data):
        out = {}
        incr = {}
        push = {}
        for field, value in data.iteritems():
            field, operator = split_field_operator(field)
            if operator == 'incr':
                incr[field] = value
            elif operator == 'push':
                push[field] = value
            else:
                out[field] = value
        if incr:
            out['$inc'] = incr
        if push:
            out['$push'] = push
        return out