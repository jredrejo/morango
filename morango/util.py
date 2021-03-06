import functools
import logging
import sqlite3
import os

from morango.constants.file import SQLITE_VARIABLE_FILE_CACHE

logger = logging.getLogger(__name__)


# taken from https://github.com/FactoryBoy/factory_boy/blob/master/factory/django.py#L256
class mute_signals(object):
    """Temporarily disables and then restores any django signals.
    Args:
        *signals (django.dispatch.dispatcher.Signal): any django signals
    Examples:
        with mute_signals(pre_init):
            user = UserFactory.build()
            ...
        @mute_signals(pre_save, post_save)
        class UserFactory(factory.Factory):
            ...
        @mute_signals(post_save)
        def generate_users():
            UserFactory.create_batch(10)
    """

    def __init__(self, *signals):
        self.signals = signals
        self.paused = {}

    def __enter__(self):
        for signal in self.signals:
            logger.debug('mute_signals: Disabling signal handlers %r',
                         signal.receivers)

            # Note that we're using implementation details of
            # django.signals, since arguments to signal.connect()
            # are lost in signal.receivers
            self.paused[signal] = signal.receivers
            signal.receivers = []

    def __exit__(self, exc_type, exc_value, traceback):
        for signal, receivers in self.paused.items():
            logger.debug('mute_signals: Restoring signal handlers %r',
                         receivers)

            signal.receivers = receivers
            with signal.lock:
                # Django uses some caching for its signals.
                # Since we're bypassing signal.connect and signal.disconnect,
                # we have to keep messing with django's internals.
                signal.sender_receivers_cache.clear()
        self.paused = {}

    def copy(self):
        return mute_signals(*self.signals)

    def __call__(self, callable_obj):
        @functools.wraps(callable_obj)
        def wrapper(*args, **kwargs):
            # A mute_signals() object is not reentrant; use a copy every time.
            with self.copy():
                return callable_obj(*args, **kwargs)
        return wrapper

def max_parameter_substitution():
    """
    SQLite has a limit on the max number of variables allowed for parameter substitution. This limit is usually 999, but
    can be compiled to a different number. This function calculates what the max is for the sqlite version running on the device.
    We use the calculated value to chunk our SQL bulk insert statements when deserializing from the store to the app layer.
    """
    if os.path.isfile(SQLITE_VARIABLE_FILE_CACHE):
        return
    conn = sqlite3.connect(':memory:')
    low = 1
    high = 1000  # hard limit for SQLITE_MAX_VARIABLE_NUMBER <http://www.sqlite.org/limits.html>
    conn.execute('CREATE TABLE T1 (id C1)')
    while low < high - 1:
        guess = (low + high) // 2
        try:
            statement = 'select * from T1 where id in (%s)' % ','.join(['?' for _ in range(guess)])
            values = [i for i in range(guess)]
            conn.execute(statement, values)
        except sqlite3.DatabaseError as ex:
            if 'too many SQL variables' in str(ex):
                high = guess
            else:
                raise
        else:
            low = guess
    conn.close()
    with open(SQLITE_VARIABLE_FILE_CACHE, 'w') as file:
        file.write(str(low))
