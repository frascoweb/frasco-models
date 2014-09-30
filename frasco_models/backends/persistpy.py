from __future__ import absolute_import
from frasco_models import Backend, QueryFilter, QueryFilterGroup
from persistpy import *
from ..utils import clean_proxy


class PersistpyBackend(Backend):
    name = "persistpy"
    operator_mapping = dict([(QueryFilter.NE, "$ne"), (QueryFilter.GT, "$gt"), (QueryFilter.GTE, "$gte"),
                        (QueryFilter.LT, "$lt"), (QueryFilter.LTE, "$lte"), (QueryFilter.IN, "$in"),
                        (QueryFilter.NIN, "$nin")])

    def __init__(self, app, options):
        self.client = MongoClient(options.get("url", "localhost"))
        self.session = Session(self.client[options["db"]])
        self.Model = self.session.create_model_base()

    def ensure_model(self, name):
        return self.session.mapper.ensure_model(name)

    def ensure_fields(self, name, fields):
        model = self.session.mapper.ensure_model(name)
        for name, spec in fields.iteritems():
            type = spec.pop("type", None)
            if type in (list, dict) and "default" not in spec:
                spec["default"] = type
            model.ensure(**dict([(name, Field(**spec))]))

    def find(self, model, pk):
        if not isinstance(pk, ObjectId):
            pk = ObjectId(pk)
        return model.query.filter_by(_id=pk).first()

    def find_all(self, query):
        return self._transform_query(query).all()

    def find_first(self, query):
        return self._transform_query(query).first()

    def find_one(self, query):
        return self._transform_query(query).first()

    def count(self, query):
        return self._transform_query(query).count()

    def save(self, obj):
        return self.session.save(obj)

    def delete(self, obj):
        return self.session.delete(obj)

    def _transform_query(self, q):
        pq = q.model.query
        if q._filters:
            pq._spec = self._transform_query_filter_group(q._filters, "$and")
        if q._order_by:
            pq._sort = [(k, 1 if v == "ASC" else -1) for k, v in q._order_by]
        if q._offset:
            pq._skip = q._offset
        if q._limit:
            pq._limit = q._limit
        return pq

    def _transform_query_filter_group(self, group, operator=None):
        conditions = []
        for filter in group:
            if isinstance(filter, QueryFilterGroup):
                conditions.append(self._transform_query_filter_group(filter))
            else:
                conditions.append(self._transform_query_filter(filter))
        if operator is None:
            operator = "$or" if group.operator == QueryFilterGroup.OR else "$and"
        return dict([(operator, conditions)])

    def _transform_query_filter(self, filter):
        v = filter.value
        if filter.field == '_id' and not isinstance(v, ObjectId):
            v = ObjectId(v)
        if filter.operator != QueryFilter.EQ:
            if filter.operator not in self.operator_mapping:
                raise Exception("Operator '%s' is not recognized by Mongo" % filter.operator)
            if filter.operator == QueryFilter.IN:
                v = [v]
            v = dict([(self.operator_mapping[filter.operator], v)])
        return dict([(filter.field, clean_proxy(v))])