from frasco import current_app
from frasco.utils import ContextStack, DelayedCallsContext
from contextlib import contextmanager
import functools
from werkzeug.local import LocalProxy


__all__ = ('Transaction', 'transaction', 'current_transaction', 'commit', 'rollback',\
           'as_transaction', 'delayed_tx_calls')


_transaction_ctx = ContextStack()
current_transaction = _transaction_ctx.make_proxy()
delayed_tx_calls = DelayedCallsContext()

class Transaction(object):
    def __init__(self, begin=True, isolated=False):
        self.ended = False
        self.isolated = isolated
        if begin:
            self.begin()

    @property
    def backend(self):
        return current_app.features.models.backend

    def begin(self):
        if self.isolated or _transaction_ctx.top:
            self.backend.begin_transaction()
        _transaction_ctx.push(self)
        delayed_tx_calls.push()

    def commit(self):
        self.ended = True
        self.backend.commit_transaction()
        _transaction_ctx.pop()
        delayed_tx_calls.pop()

    def rollback(self):
        self.ended = True
        self.backend.rollback_transaction()
        _transaction_ctx.pop()
        delayed_tx_calls.pop(drop_calls=True)

    def add(self, obj):
        self.backend.add(obj)

    def delete(self, obj):
        self.backend.remove(obj)

    def delay_call(self, func, args, kwargs):
        return delayed_tx_calls.call(func, args, kwargs)


@contextmanager
def transaction(*args, **kwargs):
    trans = Transaction(*args, **kwargs)
    try:
        yield trans
        if not trans.ended:
            trans.commit()
    except Exception as e:
        if not trans.ended:
            trans.rollback()
        raise


def commit():
    if _transaction_ctx.top:
        _transaction_ctx.top.commit()


def rollback():
    if _transaction_ctx.top:
        _transaction_ctx.top.rollback()


def as_transaction(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with transaction():
            return func(*args, **kwargs)
    return wrapper