"""
Implements the Component class; the core class that has properties,
actions that mutate the properties, and reactions that react to the
events and changes in properties.
"""

import sys

from ._dict import Dict
from ._action import ActionDescriptor, Action
from ._reaction import ReactionDescriptor, Reaction, looks_like_method
from ._property import PropertyDescriptor
from ._emitter import Emitter
from ._loop import loop
from . import logger

def this_is_js():
    return False

setTimeout = console = None


# From six.py
def with_metaclass(meta, *bases):
    """Create a base class with a metaclass."""
    # This requires a bit of explanation: the basic idea is to make a dummy
    # metaclass for one level of class instantiation that replaces itself with
    # the actual metaclass.
    # On Python 2.7, the name cannot be unicode :/
    tmp_name = b'tmp_class' if sys.version_info[0] == 2 else 'tmp_class'
    class metaclass(meta):
        def __new__(cls, name, this_bases, d):
            return meta(name, bases, d)
    return type.__new__(metaclass, tmp_name, (), {})


def new_type(name, *args, **kwargs):
    """ Alternative for type(...) to be legacy-py compatible.
    """
    name = name.encode() if sys.version_info[0] == 2 else name
    return type(name, *args, **kwargs)


class ComponentMeta(type):
    """ Meta class for Component
    * Set the name of property desciptors.
    * Sets __actions__, __reactions__ and __properties__ attribute on the class.
    * Create some private functions (e.g. mutator functions).
    """
    
    def __init__(cls, name, bases, dct):
        finalize_component_class(cls)
        type.__init__(cls, name, bases, dct)


def make_mutator(name, *args):
    def mutator(self, *args):
        self._mutate(name, *args)
    return mutator

def make_set_action(name, func):
    def setter(self, *args):
        getattr(self, '_mutate')(name, func(*args))
    return setter


def finalize_component_class(cls):
    """ Given a class, analyse its Properties, Actions and Reactions,
    to set a list of __actions__, __properties__, and __reactions__.
    Also create private methods corresponding to the properties,
    actions and reactions.
    """
    actions = {}
    reactions = {}
    properties = {}
    emitters = {}  # todo: metitters == actions?
    
    for name in dir(cls):
        if name.startswith('__'):
            continue
        val = getattr(cls, name)
        if isinstance(val, ActionDescriptor):
            actions[name] = val
        elif isinstance(val, PropertyDescriptor):
            properties[name] = val
            val._set_name(name)  # noqa
            # Mutator function
            setattr(cls, '_set_' + name, make_mutator(name))
            # auto-setter?
            if val._setter:
                setattr(cls, 'set_' + name, ActionDescriptor(make_set_action(name, val._setter), 'set_' + name, 'Setter for %s.' % name))
        elif isinstance(val, ReactionDescriptor):
            reactions[name] = val
        elif isinstance(val, Emitter):
            emitters[name] = val
        elif isinstance(val, (Action, Reaction)):
            raise RuntimeError('Class methods can only be made actions or '
                               'reactions using the corresponding decorators '
                               '(%r)' % name)
    
    # Cache prop names
    cls.__actions__ = [name for name in sorted(actions.keys())]
    cls.__reactions__ = [name for name in sorted(reactions.keys())]
    cls.__properties__ = [name for name in sorted(properties.keys())]
    cls.__emitters__ = [name for name in sorted(emitters.keys())]
    return cls


class Component(with_metaclass(ComponentMeta, object)):
    """ Base class for objects that have properties and can emit events.
    Initial values of settable properties can be provided by passing them
    as keyword arguments.
    
    Objects of this class can emit events through their ``emit()``
    method. Subclasses can use the
    :func:`prop <flexx.event.prop>` and :func:`readonly <flexx.event.readonly>`
    decorator to create properties, and the
    :func:`connect <flexx.event.connect>` decorator to create reactions.
    Methods named ``on_foo`` are connected to the event "foo".
    
    .. code-block:: python
    
        class MyObject(event.Component):
            
            # Emitters
            
            @event.prop
            def foo(self, v=0):
                return float(v)
            
            @event.emitter
            def bar(self, v):
                return dict(value=v)  # the event to emit
            
            # Reactions
            
            @event.connect('foo')
            def handle_foo(self, *events):
                print('foo was set to', events[-1].new_value)
            
            @event.connect('bar')
            def on_bar(self, *events):
                for ev in events:
                    print('bar event was generated')
        
        ob = MyObject(foo=42)
        
        @ob.connect('foo')
        def another_foo handler(*events):
            print('foo was set %i times' % len(events))
    
    """
    
    _IS_COMPONENT = True
    
    def __init__(self, **property_values):
        
        # Init some internal variables. Note that __reactions__ is a list of
        # reaction names for this class, and __handlers a dict of reactions
        # registered to events of this object.
        self.__handlers = {}
        self.__props_being_set = {}
        self.__props_ever_set = {}
        self.__pending_events = {}
        
        init_handlers = property_values.pop('_init_handlers', True)
        
        self._disposed = False
        
        # Instantiate emitters
        for name in self.__emitters__:
            self.__handlers.setdefault(name, [])
        
        # Initialize properties with default and given values (does not emit yet)
        for name in self.__properties__:
            self.__handlers.setdefault(name, [])
            default = getattr(self.__class__, name)._default
            setattr(self, '_' + name + '_value', default)
            # func = getattr(self.__class__, name).get_func()
            # setattr(self, '_' + name + '_func', func)  # needed in set_prop()
        # for name in self.__properties__:
        #     dd = getattr(self.__class__, name)._defaults
        #     if dd:
        #         self._set_prop(name, dd[0], True)
        for name in sorted(property_values):  # sort for deterministic order
            if name in self.__properties__:
                value = property_values[name]
                func = getattr(self, 'set_' + name)
                func(value)
            else:
                cname = self.__class__.__name__
                raise AttributeError('%s does not have a property %r' % (cname, name))
        
        # Init handlers and properties now, or later? --> feature for subclasses
        if init_handlers:
            self._init_handlers()
    
    def _init_handlers(self):
        """ Initialize handlers and properties. You should only do this once,
        and only when using the object is initialized with init_handlers=False.
        """
        if self.__pending_events is None:
            return
        # Schedule a call to disable event capturing
        def stop_capturing():
            self.__pending_events = None
        loop.call_later(stop_capturing)
        # Call Python or JS version to initialize and connect the handlers
        self.__init_handlers()
    
    def __init_handlers(self):
        # Instantiate handlers (i.e. resolve connections) its enough to reference them
        for name in self.__reactions__:
            getattr(self, name)
    
    if sys.version_info > (3, 4):
        # http://eli.thegreenplace.net/2009/06/12/safely-using-destructors-in-python
        def __del__(self):
            if not self._disposed:
                loop.call_later(self.dispose)
    
    def dispose(self):
        """ Use this to dispose of the object to prevent memory leaks.
        
        Make all subscribed handlers to forget about this object, clear
        all references to subscribed handlers, disconnect all handlers
        defined on this object.
        """
        self._disposed = True
        if not this_is_js():
            logger.debug('Disposing Component instance %r' % self)
        for name, handlers in self.__handlers.items():
            for label, handler in handlers:
                handler._clear_component_refs(self)
            while len(handlers):
                handlers.pop()  # no list.clear on legacy py
        for name in self.__reactions__:
            getattr(self, name).dispose()
    
    def _handlers_changed_hook(self):
        # Called when the handlers changed, can be implemented in subclasses
        pass
    
    def _register_reaction(self, event_type, handler, force=False):
        # Register a handler for the given event type. The type
        # can include a label, e.g. 'mouse_down:foo'.
        # This is called from Handler objects at initialization and when
        # they reconnect (dynamism).
        type, _, label = event_type.partition(':')
        label = label or handler._name
        handlers = self.__handlers.get(type, None)
        if handlers is None:  # i.e. type not in self.__handlers
            handlers = []
            self.__handlers[type] = handlers
            if not force:  # ! means force
                msg = ('Event type "{}" does not exist. ' +
                       'Use "!{}" or "!foo.bar.{}" to suppress this warning.')
                msg = msg.replace('{}', type)
                if hasattr(self, 'id'):
                    msg = msg.replace('exist.', 'exist on %s.' % self.id)  # Model
                if this_is_js():
                    console.warn(msg)
                else:
                    logger.warn(msg)
        
        entry = label, handler
        if entry not in handlers:
            handlers.append(entry)
        handlers.sort(key=lambda x: x[0]+'-'+x[1]._id)
        self._handlers_changed_hook()
        # Emit any pending events
        if self.__pending_events is not None:
            if not label.startswith('reconnect_'):
                for ev in self.__pending_events.get(type, []):
                    handler._add_pending_event(label, ev)
        # Send an event to communicate the value of a property
        # if type in self.__properties__:
        #     if self.__props_ever_set.get(type, False):
        #         if not label.startswith('reconnect_'):  # Avoid recursion
        #             val = getattr(self, type)
        #             ev = Dict()  # PyScript compatible
        #             ev.type = type
        #             ev.source = self
        #             ev.new_value = ev.old_value = val
        #             handler._add_pending_event(label, ev)  # friend class
    
    def disconnect(self, type, handler=None):
        """ Disconnect handlers. 
        
        Parameters:
            type (str): the type for which to disconnect any handlers.
                Can include the label to only disconnect handlers that
                were registered with that label.
            handler (optional): the handler object to disconnect. If given,
               only this handler is removed.
        """
        # This is called from Handler objects when they dispose and when
        # they reconnect (dynamism).
        type, _, label = type.partition(':')
        handlers = self.__handlers.get(type, ())
        for i in range(len(handlers)-1, -1, -1):
            entry = handlers[i]
            if not ((label and label != entry[0]) or
                    (handler and handler is not entry[1])):
                handlers.pop(i)
        self._handlers_changed_hook()
    
    def emit(self, type, info=None):
        """ Generate a new event and dispatch to all event handlers.
        
        Arguments:
            type (str): the type of the event. Should not include a label.
            info (dict): Optional. Additional information to attach to
                the event object. Note that the actual event is a Dict object
                that allows its elements to be accesses as attributes.
        """
        info = {} if info is None else info
        type, _, label = type.partition(':')
        if len(label):
            raise ValueError('The type given to emit() should not include a label.')
        # Prepare event
        if not isinstance(info, dict):
            raise TypeError('Info object (for %r) must be a dict, not %r' %
                            (type, info))
        ev = Dict(info)  # make copy and turn into nicer Dict on py
        ev.type = type
        ev.source = self
        # Push the event to the handlers (handlers use labels for dynamism)
        if self.__pending_events is not None:
            self.__pending_events.setdefault(ev.type, []).append(ev)
        self._emit(ev)
        return ev
    
    def _emit(self, ev):
        for label, handler in self.__handlers.get(ev.type, ()):
            handler._add_pending_event(label, ev)  # friend class
    
    
    def _mutate(self, prop_name, value, kind='set', index=-1):
        """ Main mutator function. Each Component class will also have an
        auto-generated mutator function for each property.
        """
        if not isinstance(prop_name, str):
            raise TypeError("_set_prop's first arg must be str, not %s" %
                             prop_name.__class__)
        if prop_name not in self.__properties__:
            cname = self.__class__.__name__
            raise AttributeError('%s object has no property %r' % (cname, prop_name))
        
        # todo: still needed?
        # prop_being_set = self.__props_being_set.get(prop_name, None)
        # if prop_being_set:
        #     return
        
        # Prepare
        private_name = '_' + prop_name + '_value'
        self.__props_being_set[prop_name] = True
        self.__props_ever_set[prop_name] = True
        
        # Set / Emit
        value2 = value
        # If not initialized yet, set
        # if prop_being_set is None:
        #     setattr(self, private_name, value2)
        #     self.emit(prop_name, dict(new_value=value2, old_value=value2))
        #     return True
        # Otherwise only set if value has changed
        old = getattr(self, private_name)
        if this_is_js():
            is_equal = old == value2
        elif hasattr(old, 'dtype') and hasattr(value2, 'dtype'):
            import numpy as np
            is_equal = np.array_equal(old, value2)
        else:
            is_equal = type(old) == type(value2) and old == value2
        if not is_equal:
            if kind == 'set':
                setattr(self, private_name, value)
            else:
                raise NotImplementedError()
            self.emit(prop_name, dict(new_value=value2, old_value=old))
            return True
    
    def _sett_prop(self, prop_name, value, _initial=False):
        """ Set the value of a (readonly) property.
        
        Parameters:
            prop_name (str): the name of the property to set.
            value: the value to set.
        """
        # Checks
        if not isinstance(prop_name, str):
            raise TypeError("_set_prop's first arg must be str, not %s" %
                             prop_name.__class__)
        if prop_name not in self.__properties__:
            cname = self.__class__.__name__
            raise AttributeError('%s object has no property %r' % (cname, prop_name))
        prop_being_set = self.__props_being_set.get(prop_name, None)
        if prop_being_set:
            return
        # Prepare
        private_name = '_' + prop_name + '_value'
        func_name = '_' + prop_name + '_func'  # set in init in both Py and JS
        # Validate value
        self.__props_being_set[prop_name] = True
        self.__props_ever_set[prop_name] = True
        func = getattr(self, func_name)
        try:
            if this_is_js():
                value2 = func.apply(self, [value])
            elif getattr(self.__class__, prop_name)._has_self:
                value2 = func(self, value)
            else:
                value2 = func(value)
        finally:
            self.__props_being_set[prop_name] = False
        # If not initialized yet, set
        if prop_being_set is None:
            setattr(self, private_name, value2)
            self.emit(prop_name, dict(new_value=value2, old_value=value2))
            return True
        # Otherwise only set if value has changed
        old = getattr(self, private_name)
        if this_is_js():
            is_equal = old == value2
        elif hasattr(old, 'dtype') and hasattr(value2, 'dtype'):
            import numpy as np
            is_equal = np.array_equal(old, value2)
        else:
            is_equal = type(old) == type(value2) and old == value2
        if not is_equal:
            setattr(self, private_name, value2)
            self.emit(prop_name, dict(new_value=value2, old_value=old))
            return True
    
    def get_event_types(self):
        """ Get the known event types for this HasEvent object. Returns
        a list of event type names, for which there is a
        property/emitter or for which any handlers are registered.
        Sorted alphabetically.
        """
        types = list(self.__handlers)  # avoid using sorted (one less stdlib func)
        types.sort()
        return types
    
    def get_event_handlers(self, type):
        """ Get a list of handlers for the given event type. The order
        is the order in which events are handled: alphabetically by
        label.
        
        Parameters:
            type (str): the type of event to get handlers for. Should not
                include a label.
        
        """
        if not type:
            raise TypeError('get_event_handlers() missing "type" argument.')
        type, _, label = type.partition(':')
        if len(label):
            raise ValueError('The type given to get_event_handlers() '
                             'should not include a label.')
        handlers = self.__handlers.get(type, ())
        return [h[1] for h in handlers]

    # This method does *not* get transpiled
    def reaction(self, *connection_strings):
        """ Connect a function to one or more events of this instance. Can
        also be used as a decorator. See the
        :func:`connect <flexx.event.connect>` decorator for more information.
        
        .. code-block:: py
            
            h = Component()
            
            # Usage as a decorator
            @h.reaction('first_name', 'last_name')
            def greet(*events):
                print('hello %s %s' % (h.first_name, h.last_name))
            
            # Direct usage
            h.reaction(greet, 'first_name', 'last_name')
            
            # Order does not matter
            h.reaction('first_name', greet)
        
        """
        return self.__react(*connection_strings)  # calls Py or JS version
    
    def __react(self, *connection_strings):
        if (not connection_strings) or (len(connection_strings) == 1 and
                                        callable(connection_strings[0])):
            raise RuntimeError('react() needs one or more connection strings.')
        
        func = None
        if callable(connection_strings[0]):
            func = connection_strings[0]
            connection_strings = connection_strings[1:]
        elif callable(connection_strings[-1]):
            func = connection_strings[-1]
            connection_strings = connection_strings[:-1]
        
        for s in connection_strings:
            if not (isinstance(s, str) and len(s) > 0):
                raise ValueError('Connection string must be nonempty string.')
        
        def _react(func):
            if not callable(func):
                raise TypeError('react() decorator requires a callable.')
            if looks_like_method(func):
                return ReactionDescriptor(func, connection_strings, self)
            else:
                return Reaction(self, func, connection_strings)
        
        if func is not None:
            return _react(func)
        else:
            return _react
