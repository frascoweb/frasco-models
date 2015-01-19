import inflection
from werkzeug import LocalProxy
import math
from flask import current_app


def as_single_model(model):
    return inflection.underscore(model.__name__)


def as_many_models(model):
    return inflection.pluralize(as_single_model(model))


def clean_proxy(value):
    if isinstance(value, LocalProxy):
        return value._get_current_object()
    return value


def clean_kwargs_proxy(kwargs):
    for k, v in kwargs.iteritems():
        kwargs[k] = clean_proxy(v)
    return kwargs


class Pagination(object):
    def __init__(self, page, per_page, total):
        self.page = page
        self.per_page = per_page
        self.total = total
        self.nb_pages = int(math.ceil(float(self.total) / float(per_page)))

    @property
    def offset(self):
        return (self.page - 1) * self.per_page

    @property
    def prev_page(self):
        return self.page - 1 if self.page > 1 else None

    @property
    def next_page(self):
        return self.page + 1 if self.page < self.nb_pages else None

    @property
    def prev(self):
        if self.prev_page is None:
            return None
        return Pagination(self.prev_page, self.per_page, self.total)

    @property
    def next(self):
        if self.next_page is None:
            return None
        return Pagination(self.next_page, self.per_page, self.total)

    def iter_pages(self, left_edge=2, left_current=2,
                   right_current=5, right_edge=2):
        last = 0
        for num in xrange(1, self.nb_pages + 1):
            if num <= left_edge or \
               (num > self.page - left_current - 1 and \
                num < self.page + right_current) or \
               num > self.nb_pages - right_edge:
                if last + 1 != num:
                    yield None
                yield num
                last = num


class PageOutOfBoundError(Exception):
    pass


def move_obj_position_in_collection(obj, new_position, position_field='position', scope=None):
    current_position = getattr(obj, position_field, 0)
    up = new_position > current_position
    shift = -1 if up else 1
    lower_idx = min(current_position, new_position)
    lower_idx += 1 if up else 0
    upper_idx = max(current_position, new_position)
    upper_idx -= 0 if up else 1

    q = current_app.features.models.query(obj.__class__)
    if scope:
        q = q.filter(**scope)
    q = q.filter(**dict([('%s__gte' % position_field, lower_idx), ('%s__lte' % position_field, upper_idx)]))
    q.update(dict([('%s__incr' % position_field, shift)]))

    setattr(obj, position_field, new_position)
    obj.save()


def ensure_unique_value(model, column, value, fallback=None, counter_start=1):
    if not fallback:
        fallback = value + "-%(counter)s"
    counter = counter_start
    q = current_app.features.models.query(model)
    while q.filter(**dict([(column, value)])).count() > 0:
        value = fallback % {'counter': counter}
        counter += 1
    return value