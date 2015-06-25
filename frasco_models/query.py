from frasco import abort
import operator


def Q(**kwargs):
    return kwargs.items()


def and_(*args):
    return {"$and": args}


def or_(*args):
    return {"$or": args}


class QueryError(Exception):
    pass


class MultipleResultError(QueryError):
    pass


class NoResultError(QueryError):
    pass


class Query(object):
    ASC = "ASC"
    DESC = "DESC"

    def __init__(self, model, backend):
        self.model = model
        self.backend = backend
        self._fields = set()
        self._filters = []
        self._order_by = []
        self._offset = None
        self._limit = None

    def get(self, id):
        return self.backend.find_by_id(self.model, id)

    def get_or_404(self, id):
        obj = self.backend.find_by_id(self.model, id)
        if obj is None:
            abort(404)
        return obj

    def select(self, *args):
        return self.clone(_fields=args)

    def filter(self, *grouped_filters, **filters):
        q = self.clone()
        q._filters.extend(grouped_filters)
        q._filters.extend(filters.items())
        return q

    def order_by(self, field, direction=None):
        q = self.clone()
        if field is None:
            q._order_by = []
            return q
        if not isinstance(field, (list, tuple)):
            field = map(str.strip, field.split(','))
        for f in field:
            d = direction or self.ASC
            if isinstance(f, tuple):
                (f, d) = f
            elif " " in f:
                (f, d) = f.rsplit(" ", 1)
            q._order_by.append((f, d.upper()))
        return q

    def offset(self, offset):
        return self.clone(_offset=offset)

    def limit(self, limit):
        return self.clone(_limit=limit)

    def clone(self, **overrides):
        attr_to_clone = ('_fields', '_filters', '_order_by', '_offset', '_limit')
        data = {}
        for attr in attr_to_clone:
            v = getattr(self, attr)
            if isinstance(v, dict):
                data[attr] = dict(**v)
            elif isinstance(v, list):
                data[attr] = list(v)
            else:
                data[attr] = v
        data.update(overrides)
        q = self.__class__(self.model, self.backend)
        q.__dict__.update(data)
        return q

    def all(self):
        return self.backend.find_all(self)

    def first(self):
        return self.backend.find_first(self)

    def first_or_404(self):
        obj = self.first()
        if obj is None:
            abort(404)
        return obj

    def one(self):
        return self.backend.find_one(self)

    def count(self):
        return self.backend.count(self)

    def update(self, data):
        return self.backend.update(self, data)

    def delete(self):
        return self.backend.delete(self)

    def for_json(self):
        return {"model": self.model.__class__.__name__,
                "fields": self._fields,
                "filters": self._filters,
                "order_by": self._order_by,
                "offset": self._offset,
                "limit": self._limit}

    def __iter__(self):
        return iter(self.all())

    def __len__(self):
        return self.count()

    def __repr__(self):
        return "Query(fields=%s, filters=%s, order_by=%s, limit=%s, offset=%s)" %\
            (self._fields, self._filters, self._order_by, self._limit, self._offset)


known_operators = ('eq', 'ne', 'lt', 'lte', 'gt', 'gte', 'in', 'nin', 'contains',
                   'incr', 'push')

operators_mapping = {
    'eq': operator.eq,
    'ne': operator.ne,
    'lt': operator.lt,
    'lte': operator.le,
    'gt': operator.gt,
    'gte': operator.ge
}


def split_field_operator(field, check_operator=True, with_python_operator=False):
    operator = 'eq'
    if '__' in field:
        field, operator = field.split('__', 1)
    if check_operator and operator not in known_operators:
        raise QueryError("Unknown operator '%s'" % operator)
    if with_python_operator:
        return field, operator, operators_mapping.get(operator)
    return field, operator