from frasco import abort


class QueryFilter(object):
    EQ = "="
    NE = "!="
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    IN = "in"
    NIN = "nin"

    operators = [EQ, NE, GT, GTE, LT, LTE, IN, NIN]

    def __init__(self, field, value, operator=EQ):
        self.field = field
        self.value = value
        self.operator = operator

    def __repr__(self):
        return "%s%s%s" % (self.field, self.operator, self.value)


class QueryFilterGroup(list):
    AND = "AND"
    OR = "OR"

    @classmethod
    def from_dict(cls, filters):
        obj = cls()
        for k, v in filters.iteritems():
            obj.append(QueryFilter(k, v))
        return obj

    def __init__(self, iter=None, operator=AND):
        if iter is None:
            iter = []
        super(QueryFilterGroup, self).__init__(iter)
        self.operator = operator

    def __repr__(self):
        return (" %s " % self.operator).join([repr(o) for o in self])


def and_(*args):
    return QueryFilterGroup(args)


def or_(*args):
    return QueryFilterGroup(args, QueryFilterGroup.OR)


class QueryError(Exception):
    pass


class MultipleResultError(QueryError):
    pass


class NoResultError(QueryError):
    pass


class Query(object):
    ASC = "ASC"
    DESC = "DESC"

    def __init__(self, model, backend=None):
        self.model = model
        self.backend = backend
        self._fields = set()
        self._filters = []
        self._order_by = []
        self._offset = None
        self._limit = None

    def get(self, pk):
        return self.backend.find(self.model, pk)

    def get_or_404(self, pk):
        obj = self.backend.find(self.model, pk)
        if obj is None:
            abort(404)
        return obj

    def select(self, *args):
        return self.clone(_fields=args)

    def filter(self, *args):
        q = self.clone()
        for f in args:
            q._filters.append(f)
        return q

    def filter_by(self, **filters):
        q = self.clone()
        for field, value in filters.iteritems():
            operator = QueryFilter.EQ
            for op in QueryFilter.operators:
                if field.endswith(op):
                    operator = op
                    field = field[:-len(op)].rstrip()
                    break
            q._filters.append(QueryFilter(field, value, operator))
        return q

    def op(self, field, operator, value):
        return QueryFilter(field, value, operator)

    def order_by(self, field, direction=None):
        q = self.clone()
        if field is None:
            q._order_by = []
            return
        if direction is None:
            if isinstance(field, tuple):
                (field, direction) = field
            elif " " in field:
                (field, direction) = field.rsplit(" ", 1)
            else:
                direction = self.ASC

        q._order_by.append((field, direction.upper()))
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
                data[attr] = dict(v)
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

    def __iter__(self):
        return self.all()

    def __len__(self):
        return self.count()

    def __repr__(self):
        return "Query(fields=%s, filters=%s, order_by=%s, limit=%s, offset=%s)" %\
            (self._fields, self._filters, self._order_by, self._limit, self._offset)