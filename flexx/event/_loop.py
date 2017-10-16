"""
Implementation of basic event loop object. Can be integrated a real
event loop such as tornado or Qt.
"""

import sys
import threading

from . import logger

# todo: maybe this can be the base class for the tornado loop that we use in flexx.app


class Loop:
    """ A simple proxy event loop. There is one instance in 
    ``flexx.event.loop``. This is used by handlers to register the
    handling of pending events. Users typically don't need to be aware
    of this.
    
    This proxy can integrate with an existing event loop (e.g. of Qt
    and Tornado). If Qt or Tornado is imported at the time that
    ``flexx.event`` gets imported, the loop is integrated automatically.
    This object can also be used as a context manager; events get
    processed when the context exits.
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        self._calllaterfunc = lambda x: None
        self.reset()
        
    def reset(self):
        """ Reset the loop, allowing for reuse.
        """
        self._last_thread_id = 0
        self._scheduled_update = False
        
        self._prop_access = {}
        self._pending_calls = []
        self._pending_actions = []
        self._pending_reactions = []
        self._pending_reaction_ids = {}
    
    def call_later(self, func):
        """ Call the given function in the next iteration of the event loop.
        """
        with self._lock:
            self._pending_calls.append(func)
            if not self._scheduled_update:
                self._scheduled_update = True
                self._calllaterfunc(self.iter)
    
    def iter(self):
        """ Do one event loop iteration; process all pending function calls.
        """
        # Check that event loop is not run from multiple threads at once
        tid = threading.get_ident()
        if self._last_thread_id and self._last_thread_id != tid:
            raise RuntimeError('Flexx is not supposed to run multiple event '
                               'loops at once.')
        self._last_thread_id = tid
        
        # Get pending call-laters and actions
        with self._lock:
            self._scheduled_update = False
            pending_calls = self._pending_calls
            self._pending_calls = []
            pending_actions = self._pending_actions
            self._pending_actions = []
        
        # Process regular call laters and such
        for i in range(len(pending_calls)):
            func = pending_calls[i]
            try:
                func()
            except Exception as err:
                logger.exception(err)
        
        # Process actions
        for i in range(len(pending_actions)):
            ob, func, args = pending_actions[i]
            try:
                func(ob, *args)
            except Exception as err:
                logger.exception(err)
        
        # Get pending reactions (reactions can only be added from handling actions)
        with self._lock:
            pending_reactions = self._pending_reactions
            pending_reaction_ids = self._pending_reaction_ids
            self._pending_reactions = []
            self._pending_reaction_ids = {}
        
        # Process reactions
        for i in range(len(pending_reactions)):
            reaction, label, _, events = pending_reactions[i]
            # Reconnect explicit reaction
            if reaction.is_explicit():
                events = reaction.filter_events(events)
            # Call reaction
            if len(events) > 0 or not reaction.is_explicit():
                self._prop_access = {}
                try:
                    reaction(*events)
                except Exception as err:
                    logger.exception(err)
            # Reconnect implicit reaction
            try:
                a_container_was_changed = pending_reaction_ids[reaction._id]
                if not reaction.is_explicit() and a_container_was_changed:
                    connections = []
                    for component, names in self._prop_access.values():
                        for name in names:
                            connections.append((component, name))
                    reaction.update_implicit_connections(connections)
            finally:
                self._prop_access = {}
    
    def add_action_invokation(self, ob, func, args):
        with self._lock:
            self._pending_actions.append((ob, func, args))
    
    def add_reaction_event(self, reaction, label, ev):
        # todo: do we need the label here ?
        
        # _pending_reactions is a list of tuples (reaction, label, representing event, events)
        # _pending_reaction_ids maps reaction._id -> whether a container prop changed
        #
        # We try to consolidate events here, as they are added.
        
        with self._lock:
            is_container = isinstance(ev.get('new_value', None), (tuple, list))
            
            if reaction.is_explicit():
                events = [ev]
                # Try to consolidate the events, but don't break order!
                i = len(self._pending_reactions)
                while i > 0:
                    i -= 1
                    ev2 = self._pending_reactions[i][-2]  # representing event
                    if self._pending_reactions[i][0] is reaction:
                        # We can simply append the event. Update the representing event
                        self._pending_reactions[i][-1].append(ev)
                        if not (ev2.source is ev.source and ev2.type == ev.type):
                            self._pending_reactions[i][-2] = None  # events are heterogeneous
                        return
                    # Only continue if all events of the next item matches the current event
                    if not (ev2 and ev2.source is ev.source and ev2.type == ev.type):
                        break
            
            else:
                events = []
                # Try to consolidate the events, order does not matter now.
                if reaction._id in self._pending_reaction_ids:
                    self._pending_reaction_ids[reaction._id] |= is_container
                    return
            
            self._pending_reactions.append((reaction, label, ev, events))
            self._pending_reaction_ids[reaction._id] = is_container  # reaction
    
    def register_prop_access(self, component, prop_name):
        # todo: check that we are processing reactions right now
        # todo: only try to reconnect when a property that is a list/tuple changes
        # Note that we use a dict here, but for the event reconnecting to
        # be efficient, the order of connections is imporant, so implicit
        # reactions have really poor performance on Python 2.7 :)
        # Make sure not to count access from other threads
        if threading.get_ident() == self._last_thread_id:
            if component._id not in self._prop_access:
                self._prop_access[component._id] = component, {prop_name: True}
            else:
                self._prop_access[component._id][1][prop_name] = True
    
    def __enter__(self):
        return self
    
    def __exit__(self, type, value, traceback):
        self.iter()
    
    def integrate(self, call_later_func=None, raise_on_fail=True):
        """ Integrate with an existing event loop system.
        
        Params:
            call_later_func (func): a function that can be called to
                schedule the calling of a given function. If not given,
                will try to connect to Tornado or Qt event loop, but only
                if either library is already imported.
            raise_on_fail (bool): whether to raise an error when the
                integration could not be performed.
        """
        if call_later_func is not None:
            if callable(call_later_func):
                self._calllaterfunc = call_later_func
                self._calllaterfunc(self.iter)
            else:
                raise ValueError('call_later_func must be a function')
        elif 'tornado' in sys.modules:
            self.integrate_tornado()
        elif 'PyQt4.QtGui' in sys.modules:  # pragma: no cover
            self.integrate_pyqt4()
        elif 'PySide.QtGui' in sys.modules:  # pragma: no cover
            self.integrate_pyside()
        elif raise_on_fail:  # pragma: no cover
            raise RuntimeError('Could not integrate flexx.event loop')
    
    def integrate_tornado(self):
        """ Integrate with tornado.
        """
        import tornado.ioloop
        loop = tornado.ioloop.IOLoop.current()
        self._calllaterfunc = loop.add_callback
        self._calllaterfunc(self.iter)
        logger.debug('Flexx event loop integrated with Tornado')
    
    def integrate_pyqt4(self):  # pragma: no cover
        """ Integrate with PyQt4.
        """
        from PyQt4 import QtCore, QtGui
        self._integrate_qt(QtCore, QtGui)
        logger.debug('Flexx event loop integrated with PyQt4')
    
    def integrate_pyside(self):  # pragma: no cover
        """ Integrate with PySide.
        """
        from PySide import QtCore, QtGui
        self._integrate_qt(QtCore, QtGui)
        logger.debug('Flexx event loop integrated with PySide')
    
    def _integrate_qt(self, QtCore, QtGui):  # pragma: no cover
        from queue import Queue, Empty
        
        class _CallbackEventHandler(QtCore.QObject):
            
            def __init__(self):
                QtCore.QObject.__init__(self)
                self.queue = Queue()
            
            def customEvent(self, event):
                while True:
                    try:
                        callback, args = self.queue.get_nowait()
                    except Empty:
                        break
                    try:
                        callback(*args)
                    except Exception as why:
                        print('callback failed: {}:\n{}'.format(callback, why))
            
            def postEventWithCallback(self, callback, *args):
                self.queue.put((callback, args))
                QtGui.qApp.postEvent(self, QtCore.QEvent(QtCore.QEvent.User))
        
        _callbackEventHandler = _CallbackEventHandler()
        self._calllaterfunc = _callbackEventHandler.postEventWithCallback
        self._calllaterfunc(self.iter)


loop = Loop()
loop.integrate(None, False)
