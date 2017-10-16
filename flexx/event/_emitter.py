"""
Implements the emitter decorator, class and desciptor.
"""

import inspect

from ._action import BaseDescriptor



# todo:  I think we can use actions for this! If an action returns a dict, it is emitted as an event!
# todo:  or ... should emitted events end up in the reaction queue?

def emitter(func):
    """ Decorator to turn a Component's method into an emitter.
    
    An emitter makes it easy to emit specific events and functions as a placeholder
    for documenting an event.
    
    .. code-block:: python
    
        class MyObject(event.Component):
           
           @emitter
           def spam(self, v):
                return dict(value=v)
        
        m = MyObject()
        m.spam(42)
    
    The method can have any number of arguments, and should return a
    dictionary that represents the event to generate. The method's
    docstring is used as the emitter's docstring.
    """
    if not callable(func):
        raise TypeError('emitter decorator needs a callable')
    return Emitter(func, func.__name__, func.__doc__)


class BaseEmitter:
    """ Base class for descriptors used for generating events.
    """
    
    def __init__(self, func, name=None, doc=None):
        assert callable(func)
        self._func = func
        self._name = name or 'anonymous'
        self._doc = doc
        self._set_name(name)  # updated by Component meta class
        
    
    def _set_name(self, name):
        self._name = name  # or func.__name__
        self.__doc__ = '*%s*: %s' % (self.__class__.__name__.lower(),
                                     self._doc or self._func.__doc__ or self._name)
    
    def __repr__(self):
        cls_name = self.__class__.__name__
        return '<%s for %s at 0x%x>' % (cls_name, self._name, id(self))
    
    def get_func(self):
        """ Get the corresponding function object.
        """
        return self._func


class Emitter(BaseEmitter):
    """ Placeholder for documentation and easy emitting of the event.
    """
    
    def __set__(self, instance, value):
        raise AttributeError("Can't set emitter attribute %r" % self._name)
    
    def __delete__(self, instance):
        raise AttributeError('Cannot delete emitter attribute %r.' % self._name)
    
    def __get__(self, instance, owner):
        if instance is None:
            return self
        def func(*args):  # this func should return None, so super() works correct
            ev = self._func(instance, *args)
            if ev is not None:
                instance.emit(self._name, ev)
        func.__doc__ = self.__doc__
        return func
