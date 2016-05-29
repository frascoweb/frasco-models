from __future__ import absolute_import
from frasco import copy_extra_feature_options
from frasco.utils import JSONEncoder
from frasco_models import Backend, ModelSchemaError, and_, split_field_operator
from frasco_models.utils import clean_proxy
from flask_mongoengine import (MongoEngine, Document as FlaskDocument,\
                                   DynamicDocument as FlaskDynamicDocument,\
                                   BaseQuerySet as FlaskQuerySet)
from mongoengine import Q, DynamicDocument as BaseDynamicDocument, ListField
from mongoengine.base import get_document, BaseDocument
from pymongo.read_preferences import ReadPreference
from bson import json_util
from bson.objectid import ObjectId


class MongoEngineJSONEncoder(JSONEncoder):
    """A JSONEncoder which provides serialization of MongoEngine documents
    """
    def default(self, obj):
        if isinstance(obj, BaseDocument) and not getattr(obj, 'for_json', None):
            return json_util._json_convert(obj.to_mongo())
        return JSONEncoder.default(self, obj)


class BaseQuerySet(FlaskQuerySet):
    """QuerySet with a for_json() method for easy encoding"""
    def for_json(self):
        return list(self.all())


class Document(FlaskDocument):
    meta = {'abstract': True,
            'queryset_class': BaseQuerySet}

    def __taskdump__(self):
        return 'frasco::current_app.features.models[%s]' % self.__class__.__name__, str(self.id)

    @classmethod
    def __taskload__(cls, id):
        return cls.objects.get(id=id)

    ######################################################
    #### BACKPORT FROM DEV VERSION
    ######################################################
    def reload(self, *fields, **kwargs):
        """Reloads all attributes from the database.
        :param fields: (optional) args list of fields to reload
        :param max_depth: (optional) depth of dereferencing to follow
        .. versionadded:: 0.1.2
        .. versionchanged:: 0.6  Now chainable
        .. versionchanged:: 0.9  Can provide specific fields to reload
        """
        max_depth = 1
        if fields and isinstance(fields[0], int):
            max_depth = fields[0]
            fields = fields[1:]
        elif "max_depth" in kwargs:
            max_depth = kwargs["max_depth"]

        if not self.pk:
            raise self.DoesNotExist("Document does not exist")
        obj = self._qs.read_preference(ReadPreference.PRIMARY).filter(
            **self._object_key).only(*fields).limit(1
                                                    ).select_related(max_depth=max_depth)

        if obj:
            obj = obj[0]
        else:
            raise self.DoesNotExist("Document does not exist")

        for field in self._fields_ordered:
            if not fields or field in fields:
                try:
                    setattr(self, field, self._reload(field, obj[field]))
                except KeyError:
                    # If field is removed from the database while the object
                    # is in memory, a reload would cause a KeyError
                    # i.e. obj.update(unset__field=1) followed by obj.reload()
                    delattr(self, field)

        # BUG FIX BY US HERE:
        if not fields:
            self._changed_fields = obj._changed_fields
        else:
            for field in fields:
                field = self._db_field_map.get(field, field)
                if field in self._changed_fields:
                    self._changed_fields.remove(field)
        self._created = False
        return self
    ######################################################
    ######################################################


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
        self.db.SetField = SetField
        # Flask-MongoEngine overrides the json_encoder but their
        # version ignores if for_json() is defined
        app.json_encoder = MongoEngineJSONEncoder

    def ensure_model(self, name):
        if isinstance(name, FlaskDocument):
            return name
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
        operator, filters = group.items()[0]
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


class SetField(ListField):
    """ Set field.

        Extends ListField, so that's how it's represented in Mongo.
    """
    def __set__(self, instance, value):
        return super(SetField, self).__set__(instance, set(value or []))

    def to_mongo(self, value):
        return super(SetField, self).to_mongo(list(value))

    def to_python(self, value):
        return set(super(SetField, self).to_python(value))

    def validate(self, value):
        if not isinstance(value, set):
            self.error('Only sets may be used.')