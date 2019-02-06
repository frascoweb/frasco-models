from frasco import current_app
from frasco.utils import ContextStack, DelayedCallsContext
from contextlib import contextmanager
import functools
from werkzeug.local import LocalProxy


__all__ = ('transaction', 'current_transaction', 'as_transaction', 'delayed_tx_calls')


_transaction_ctx = ContextStack(False, True)
current_transaction = _transaction_ctx.make_proxy()
delayed_tx_calls = DelayedCallsContext()


@contextmanager
def transaction():
    if not _transaction_ctx.top:
        current_app.logger.debug('BEGIN TRANSACTION')
    _transaction_ctx.push()
    delayed_tx_calls.push()
    try:
        yield
        _transaction_ctx.pop()
        if not _transaction_ctx.top:
            current_app.logger.debug('COMMIT TRANSACTION')
            current_app.features.models.backend.commit_transaction()
        else:
            current_app.features.models.backend.flush_transaction()
        delayed_tx_calls.pop()
    except:
        _transaction_ctx.pop()
        if not _transaction_ctx.top:
            current_app.logger.debug('ROLLBACK TRANSACTION')
            current_app.features.models.backend.rollback_transaction()
        delayed_tx_calls.pop(drop_calls=True)
        raise


def as_transaction(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with transaction():
            return func(*args, **kwargs)
    return wrapper
