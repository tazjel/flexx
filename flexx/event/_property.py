"""
Implements the property decorator, class and desciptor.
"""

from ._loop import loop
from ._action import BaseDescriptor


class Property(BaseDescriptor):
    """ Class descriptor for properties.
    """
    
    _default = None
    
    def __init__(self, *args, doc='', settable=False):
        # Set default
        if len(args) > 1:
            raise TypeError('event.Property() accepts at most 1 positional argument.')
        elif len(args) == 1:
            self._default = args[0]
            if callable(self._default):
                raise TypeError('event.Property() is not a decorator (anymore).')
        # Set doc
        if not isinstance(doc, str):
            raise TypeError('event.Property() doc must be a string.')
        self._doc = doc
        # Set settable
        self._settable = bool(settable)
        
        self._set_name('anonymous_property')
    
    def _set_name(self, name):
        self._name = name  # or func.__name__
        self.__doc__ = '*property*: %s' % (self._doc or self._name)
                                     
    def __set__(self, instance, value):
        t = 'Cannot set property %r; properties can only be mutated by actions.'
        raise AttributeError(t % self._name)
    
    def __get__(self, instance, owner):
        if instance is None:
            return self
        private_name = '_' + self._name + '_value'
        loop.register_prop_access(instance, self._name)
        return getattr(instance, private_name)
    
    def make_mutator(self):
        name = self._name
        def mutator(self, *args):
            return self._mutate(name, *args)
        return mutator
    
    def make_set_action(self):
        name = self._name
        def setter(self, val):
            self._mutate(name, val)
        return setter
    
    def _validate(self, value):
        raise NotImplementedError('Cannot use Property; '
                                  'use one of the subclasses instead.')


# todo: these need docs!

class AnyProp(Property):
    
    _default = None
    
    def _validate(self, value):
        return value


class BoolProp(Property):
    
    _default = False
    
    def _validate(self, value):
        return bool(value)


class IntProp(Property):
    
    _default = 0
    
    def _validate(self, value):
        if isinstance(value, (int, float)) or isinstance(value, str):
            return int(value)
        else:
            raise TypeError('%s property cannot accept %s.' %
                            (self.__class__.__name__, value.__class__.__name__))


class FloatProp(Property):
    
    _default = 0.0
    
    def _validate(self, value):
        if isinstance(value, (int, float)) or isinstance(value, str):
            return float(value)
        else:
            raise TypeError('%s property cannot accept %s.' %
                            (self.__class__.__name__, value.__class__.__name__))


class StringProp(Property):
    
    _default = ''
    
    def _validate(self, value):
        if not isinstance(value, str):
            raise TypeError('%s property cannot accept %s.' %
                            (self.__class__.__name__, value.__class__.__name__))
        return value


class TupleProp(Property):
    
    _default = ()
    
    def _validate(self, value):
        if not isinstance(value, (tuple, list)):
            raise TypeError('%s property cannot accept %s.' %
                            (self.__class__.__name__, value.__class__.__name__))
        return tuple(value)


# todo: test in both that initializing a prop gives a new list instance
class ListProp(Property):
    
    _default = []
    
    def _validate(self, value):
        if not isinstance(value, (tuple, list)):
            raise TypeError('%s property cannot accept %s.' %
                            (self.__class__.__name__, value.__class__.__name__))
        return list(value)


class ComponentProp(Property):
    
    _default = None
    
    def _validate(self, value):
        if not (value is None or isinstance(value, Component)):
            raise TypeError('%s property cannot accept %s.' %
                            (self.__class__.__name__, value.__class__.__name__))
        return value


# todo: For more complex stuff, maybe introduce an EitherProp, e.g. String or None.
# EiterProp would be nice, like Bokeh has. Though perhaps its already fine if
# props can be nullable. Note that people can also use AnyProp as a fallback.
# 
# class NullProp(Property):
#     
#     def _validate(self, value):
#         if not value is None:
#             raise TypeError('Null property can only be None.')
# 
# class EitherProp(Property):
#     
#     def __init__(self, *prop_classes, **kwargs):
#         self._sub_classes = prop_classes
#     
#     def _validate(self, value):
#         for cls in self._sub_classes:
#             try:
#                 return cls._validate(self, value)
#             except TypeError:
#                 pass
#             raise TypeError('This %s property cannot accept %s.' %
#                             (self.__class__.__name__, value.__class__.__name__))

# todo: more special properties
# class Auto -> Bokeh has special prop to indicate "automatic" value
# class Color -> I like this, is quite generic
# class Date, DateTime
# class Enum
# class Either
# class Instance
# class Array
# class MinMax


__all__ = []
for name, cls in list(globals().items()):
    if isinstance(cls, type) and issubclass(cls, Property):
        __all__.append(name)

del name, cls

# Delayed import; deal with circular ref
from ._component import Component
