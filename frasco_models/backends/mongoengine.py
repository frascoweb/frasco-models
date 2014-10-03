from __future__ import absolute_import
from frasco import copy_extra_feature_options
from frasco.utils import JSONEncoder
from frasco_models import Backend, ModelSchemaError, and_, split_field_operator
from frasco_models.utils import clean_proxy
from flask.ext.mongoengine import (MongoEngine, Document as FlaskDocument,\
                                   DynamicDocument as FlaskDynamicDocument,\
                                   BaseQuerySet as FlaskQuerySet)
from mongoengine import Q, DynamicDocument as BaseDynamicDocument
from mongoengine.base import get_document, BaseDocument
from bson import json_util
from bson.objectid import ObjectId


class MongoEngineJSONEncoder(JSONEncoder):
    """A JSONEncoder which provides serialization of MongoEngine documents
    """
    def default(self, obj):
        if isinstance(obj, BaseDocument) and not getattr(obj, 'for_json', None):
            return json_util._json_convert(obj.to_mongo())
        return superclass.default(self, obj)


class BaseQuerySet(FlaskQuerySet):
    """QuerySet with a for_json() method for easy encoding"""
    def for_json(self):
        return list(self.all())


class Document(FlaskDocument):
    meta = {'abstract': True,
            'queryset_class': BaseQuerySet}


class DynamicDocument(FlaskDynamicDocument):
    meta = {'abstract': True,
            'queryset_class': BaseQuerySet}


class MongoengineBackend(Backend):
    name = "mongoengine"

    def __init__(self, app, options):
        super(MongoengineBackend, self).__init__(app, options)
        copy_extra_feature_options(app.features.models, app.config, 'MONGODB_')
        self.db = MongoEngine(app)
        self.db.Document = Document
        self.db.DynamicDocument = DynamicDocument
        # Flask-MongoEngine overrides the json_encoder but their
        # version ignores if for_json() is defined
        app.json_encoder = MongoEngineJSONEncoder

    def ensure_model(self, name):
        return get_document(name)

    def ensure_schema(self, name, fields):
        model = self.ensure_model(name)
        if isinstance(model, BaseDynamicDocument):
            return
        for fname, _ in fields.iteritems():
            if fname not in model._fields:
                raise ModelSchemaError("Missing field '%s' in model '%s'" % (fname, name))

    def find_by_id(self, model, id):
        if not isinstance(id, ObjectId):
            id = ObjectId(id)
        return model.objects.filter(id=id).first()

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
            qs = qs(self._transform_query_filter_group(and_(*q._filters)))
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
            elif operator == '$or':
                qs |= q
            else:
                qs &= q
        return qs

    def _transform_query_filter(self, filter):
        field, value = filter
        field, operator = split_field_operator(field)
        value = clean_proxy(value)
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