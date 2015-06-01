from __future__ import absolute_import
from frasco import copy_extra_feature_options, current_app
from frasco.utils import JSONEncoder
from frasco_models import Backend, ModelSchemaError, and_, split_field_operator, QueryError
from frasco_models.utils import clean_proxy
from flask.ext.sqlalchemy import SQLAlchemy as BaseSQLAchemy, Model as BaseModel, _BoundDeclarativeMeta, _QueryProperty
from sqlalchemy.ext.declarative import declarative_base
import sqlalchemy


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


class SqlalchemyBackend(Backend):
    name = "sqllalchemy"

    def __init__(self, app, options):
        super(SqlalchemyBackend, self).__init__(app, options)
        copy_extra_feature_options(app.features.models, app.config, 'SQLALCHEMY_')
        self.db = SQLAlchemy(app)
        
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
        operator, filters = group.popitem()
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