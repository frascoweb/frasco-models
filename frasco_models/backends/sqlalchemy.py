from __future__ import absolute_import
from frasco import copy_extra_feature_options, current_app
from frasco.utils import JSONEncoder, ContextStack, DelayedCallsContext
from frasco_models import Backend, ModelSchemaError, and_, split_field_operator, QueryError
from frasco_models.utils import clean_proxy
from flask.ext.sqlalchemy import SQLAlchemy as BaseSQLAchemy, Model as BaseModel, _BoundDeclarativeMeta, _QueryProperty
from sqlalchemy.ext.declarative import declarative_base
import sqlalchemy
from sqlalchemy.inspection import inspect as sqlainspect
from sqlalchemy.sql import sqltypes
import inspect
import datetime
from contextlib import contextmanager
import functools


class Model(BaseModel):
    def __taskdump__(self):
        return 'frasco::current_app.features.models[%s]' % self.__class__.__name__, str(self.id)

    @classmethod
    def __taskload__(cls, id):
        return cls.query.get(id)


class SQLAlchemy(BaseSQLAchemy):
    def make_declarative_base(self, metadata=None):
        """Creates the declarative base."""
        base = declarative_base(cls=Model, name='Model',
                                metadata=metadata,
                                metaclass=_BoundDeclarativeMeta)
        base.query = _QueryProperty(self)
        return base


sqla_type_mapping = [
    (sqltypes.Integer, int),
    (sqltypes.Float, float),
    (sqltypes.Boolean, bool),
    (sqltypes.DateTime, datetime.datetime),
    (sqltypes.Date, datetime.date)
]


class SqlalchemyBackend(Backend):
    name = "sqlalchemy"

    def __init__(self, app, options):
        super(SqlalchemyBackend, self).__init__(app, options)
        copy_extra_feature_options(app.features.models, app.config, 'SQLALCHEMY_')
        self.db = SQLAlchemy(app, session_options=options.get('session_options'))
        
        @app.cli.command()
        def create_db():
            try:
                self.db.create_all()
            except sqlalchemy.exc.CircularDependencyError as e:
                try:
                    self.graph_circular_dependency_error(e)
                except ImportError:
                    app.logger.info('Install networkx and pygraphviz to generate a graph of the circular dependency')
                    pass
                raise e

        app.cli.command('drop_db')(self.db.drop_all)

    def ensure_model(self, name):
        if isinstance(name, self.db.Model):
            return name
        return self.db.Model._decl_class_registry[name]

    def ensure_schema(self, name, fields):
        model = self.ensure_model(name)
        for fname, _ in fields.iteritems():
            if fname not in model.__mapper__.attrs:
                raise ModelSchemaError("Missing field '%s' in model '%s'" % (fname, name))

    def inspect_fields(self, model):
        if not inspect.isclass(model):
            model = model.__class__
        mapper = sqlainspect(model)
        fields = []
        for attr in mapper.column_attrs:
            field_type = str
            for coltype, pytype in sqla_type_mapping:
                if isinstance(attr.columns[0].type, coltype):
                    field_type = pytype
                    break
            fields.append((attr.key, dict(type=field_type)))
        return fields

    def save(self, obj):
        self.db.session.add(obj)
        self.db.session.commit()

    def remove(self, obj):
        self.db.session.delete(obj)
        self.db.session.commit()

    def find_by_id(self, model, id):
        return model.query.filter_by(id=id).first()

    def find_all(self, query):
        return self._transform_query(query).all()

    def find_first(self, query):
        return self._transform_query(query).first()

    def find_one(self, query):
        return self._transform_query(query).first()

    def count(self, query):
        return self._transform_query(query).count()

    def update(self, query, data):
        return self._transform_query(query).update(
            self._prepare_data(query.model, data),
            synchronize_session=False)

    def delete(self, query):
        return self._transform_query(query).delete(
            synchronize_session=False)

    def _transform_query(self, q):
        qs = q.model.query
        if q._filters:
            qs = qs.filter(self._transform_query_filter_group(q.model, and_(*q._filters)))
        if q._order_by:
            qs = qs.order_by(*[k + ' ' + v for k, v in q._order_by])
        if q._offset:
            qs = qs.offset(q._offset)
        if q._limit:
            qs = qs.limit(q._limit)
        return qs

    def _transform_query_filter_group(self, model, group):
        operator, filters = group.items()[0]
        transformed_filters = []
        for filter in filters:
            if isinstance(filter, dict):
                q = self._transform_query_filter_group(model, filter)
                if q is None:
                    continue
            else:
                q = self._transform_query_filter(model, filter)
            transformed_filters.append(q)
        if operator == "$or":
            return sqlalchemy.or_(*transformed_filters)
        return sqlalchemy.and_(*transformed_filters)

    def _transform_query_filter(self, model, filter):
        field, value = filter
        field, operator, py_operator = split_field_operator(field, with_python_operator=True)
        value = clean_proxy(value)
        column = getattr(model, field)
        if py_operator:
            return py_operator(column, value)
        if operator == 'in':
            return column.in_(value)
        if operator == 'nin':
            return ~column.in_(value)
        raise QueryError("Cannot convert operator '%s' to sqlalchemy operator" % operator)

    def _prepare_data(self, model, data):
        out = {}
        for field, value in data.iteritems():
            field, operator = split_field_operator(field)
            column = getattr(model, field)
            if operator == 'incr':
                out[column] = column + value
            elif operator == 'push':
                raise QueryError("Operator 'push' not supported by sqlalchemy")
            else:
                out[column] = value
        return out

    def graph_circular_dependency_error(self, e, filename='sqla_circular_dep_graph.png'):
        # from: http://ilyasterin.com/blog/2014/01/cyclical-dependency-detection-in-the-database.html
        import networkx as nx
        G=nx.DiGraph()
        cycle_tables = set([t.name for t in e.cycles])
        for t in e.cycles:
            for fk in t.foreign_keys:
                table, col = fk.target_fullname.split('.')
                if (table in cycle_tables):
                    G.add_edge(t.name, table)
        agraph = nx.to_agraph(G)
        agraph.draw(filename, format='png', prog='dot')


_transaction_ctx = ContextStack()
delayed_tx_calls = DelayedCallsContext()

class Transaction(object):
    def __init__(self, begin=True, isolated=False):
        self.ended = False
        self.isolated = isolated
        if begin:
            self.begin()

    def begin(self):
        if self.isolated or _transaction_ctx.top:
            current_app.features.models.db.session.begin(subtransactions=True)
        _transaction_ctx.push(self)
        delayed_tx_calls.push()

    def commit(self):
        self.ended = True
        current_app.features.models.db.session.commit()
        _transaction_ctx.pop()
        delayed_tx_calls.pop()

    def rollback(self):
        self.ended = True
        current_app.features.models.db.session.rollback()
        _transaction_ctx.pop()
        delayed_tx_calls.pop(drop_calls=True)


@contextmanager
def transaction(*args, **kwargs):
    """Execute service calls as part of a transaction.
    Because services assumes they are the primary endpoint,
    they will always commit. However, this behavior is not
    always desire when calling services internally (eg: in the
    case you are calling many services at once). This context
    will ensure that service calls occur as part of a transaction.
    All db queries will happen in a subtransaction and push events
    and enqueued tasks will be delayed until the end of the context.
    The transaction will be commited before exciting the context.
    """
    trans = Transaction(*args, **kwargs)
    try:
        yield
        if not trans.ended:
            trans.commit()
    except Exception as e:
        if not trans.ended:
            trans.rollback()
        raise e


def commit():
    if _transaction_ctx.top:
        _transaction_ctx.top.commit()


def rollback():
    if _transaction_ctx.top:
        _transaction_ctx.top.rollback()


def as_transaction(func):
    """This decorator will wrap the function call in a transaction.
    This decorator must be used to mark service endpoints which
    needs to commit to the db.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with transaction():
            return func(*args, **kwargs)
    return wrapper