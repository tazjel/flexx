"""
Implements the Component class; the core class that has properties,
actions that mutate the properties, and reactions that react to the
events and changes in properties.
"""

import sys

from ._dict import Dict
from ._attribute import Attribute
from ._action import ActionDescriptor, Action
from ._reaction import ReactionDescriptor, Reaction, looks_like_method
from ._property import Property
from ._emitter import EmitterDescriptor
from ._loop import loop, this_is_js
from . import logger


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


def new_type(name, *args, **kwargs):  # pragma: no cover
    """ Alternative for type(...) to be legacy-py compatible.
    """
    name = name.encode() if sys.version_info[0] == 2 else name
    return type(name, *args, **kwargs)


class ComponentMeta(type):
    """ Meta class for Component
    * Set the name of property desciptors.
    * Set __actions__, __reactions__, __emitters__ and __properties__ class attributes.
    * Create private methods (e.g. mutator functions and prop validators).
    """
    
    def __init__(cls, name, bases, dct):
        cls._finish_properties(dct)
        cls._init_hook1(name, bases, dct)
        cls._set_summaries()
        cls._init_hook2(name, bases, dct)
        type.__init__(cls, name, bases, dct)
    
    def _init_hook1(cls, name, bases, dct):
        """ Overloaded in flexx.app.AppComponentMeta.
        """
        pass
    
    def _init_hook2(cls, name, bases, dct):
        """ Overloaded in flexx.app.AppComponentMeta.
        """
        pass
    
    def _set_cls_attr(cls, dct, name, att):
        dct[name] = att
        setattr(cls, name, att)
    
    def _finish_properties(cls, dct):
        """ Finish properties:
        
        * Create a mutator function for convenience.
        * Create validator function.
        * If needed, create a corresponding set_xx action.
        """
        for name in list(dct.keys()):
            if name.startswith('__'):
                continue
            val = getattr(cls, name)
            if isinstance(val, type) and issubclass(val, (Attribute, Property)):
                raise TypeError('Attributes and Properties should be instantiated, '
                                'use ``foo = IntProp()`` instead of ``foo = IntProp``.')
            elif isinstance(val, Attribute):
                val._set_name(name)  # noqa
            elif isinstance(val, Property):
                val._set_name(name)  # noqa
                # Create validator method
                cls._set_cls_attr(dct, '_' + name + '_validate', val._validate)
                # Create mutator method
                cls._set_cls_attr(dct, '_mutate_' + name, val.make_mutator())
                # Create setter action?
                action_name = 'set_' + name
                if val._settable and not hasattr(cls, action_name):
                    action_des = ActionDescriptor(val.make_set_action(), action_name,
                                                'Setter for %s.' % name)
                    cls._set_cls_attr(dct, action_name, action_des)
    
    def _set_summaries(cls):
        """ Analyse the class and set lists __actions__, __emitters__,
        __properties__, and __reactions__.
        """
        
        attributes = {}
        properties = {}
        actions = {}
        emitters = {}
        reactions = {}
        
        for name in dir(cls):
            if name.startswith('__'):
                continue
            val = getattr(cls, name)
            if isinstance(val, Attribute):
                attributes[name] = val
            elif isinstance(val, Property):
                properties[name] = val
            elif isinstance(val, ActionDescriptor):
                actions[name] = val
            elif isinstance(val, ReactionDescriptor):
                reactions[name] = val
            elif isinstance(val, EmitterDescriptor):
                emitters[name] = val
            elif isinstance(val, (Action, Reaction)):  # pragma: no cover
                raise RuntimeError('Class methods can only be made actions or '
                                   'reactions using the corresponding decorators '
                                   '(%r)' % name)
        # Cache names
        cls.__attributes__ = [name for name in sorted(attributes.keys())]
        cls.__properties__ = [name for name in sorted(properties.keys())]
        cls.__actions__ = [name for name in sorted(actions.keys())]
        cls.__emitters__ = [name for name in sorted(emitters.keys())]
        cls.__reactions__ = [name for name in sorted(reactions.keys())]


class Component(with_metaclass(ComponentMeta, object)):
    """ Base component class.
    
    Components have properties, actions that can mutate properties, and
    reactions that react to changes in properties and to other events.
    
    Initial values of properties can be provided by passing them
    as keyword arguments. This only works if a corresponding ``set_xx()``
    action is available.
    
    Objects of this class can emit events through their ``emit()``
    method. Subclasses can use :func:`Property <flexx.event.Property>` to
    define properties, and the  :func:`action <flexx.event.action>`, 
    :func:`reaction <flexx.event.reaction>`, and 
    :func:`emitter <flexx.event.emitter>` decorators to create actions,
    reactions. and emitters, respectively. 
    
    .. code-block:: python
    
        class MyComponent(event.Component):
            
            foo = evene.FloatProp(7, settable=True)
            
            @event.emitter
            def bar(self, v):
                return dict(value=v)  # the event to emit
            
            @event.action
            def inrease_foo(self):
                self._mutate_foo(self.foo + 1)
            
            @event.reaction('foo')
            def on_foo(self, *events):
                print('foo was set to', events[-1].new_value)
            
            @event.reaction('bar')
            def on_bar(self, *events):
                for ev in events:
                    print('bar event was emitted')
        
        ob = MyComponent(foo=42)
        
        @ob.reaction('foo')
        def another_foo_reaction(*events):
            print('foo was set %i times' % len(events))
    
    """
    
    _IS_COMPONENT = True
    _COUNT = 0
    
    id = Attribute(doc='The string by which this component is identified.')
    
    def __init__(self, *init_args, **property_values):
        
        Component._COUNT += 1
        self._id = self.__class__.__name__ + str(Component._COUNT)
        self._disposed = False
        
        # Init some internal variables. Note that __reactions__ is a list of
        # reaction names for this class, and __handlers a dict of reactions
        # registered to events of this object.
        # The __pending_events makes that reactions that connect to this
        # component right after it initialization get the initial events.
        self.__handlers = {}
        self.__pending_events = {}
        self.__anonymous_reactions = []
        
        # Prepare handlers with event types that we know
        for name in self.__emitters__:
            self.__handlers.setdefault(name, [])
        for name in self.__properties__:
            self.__handlers.setdefault(name, [])
        
        # Init the values of all properties.
        prop_events = self._comp_init_property_values(property_values)
        
        # Apply user-defined initialization
        with self:
            self.init(*init_args)
        
        # Connect reactions and fire initial events
        self._comp_init_reactions()
        self._comp_init_events(prop_events)
    
    def __repr__(self):
        return "<Component '%s' at 0x%x>" % (self._id, id(self))
    
    def _comp_init_property_values(self, property_values):
        events = []
        # First process default property values
        for name in self.__properties__:  # is sorted by name
            prop = getattr(self.__class__, name)
            value = getattr(self, '_' + name + '_validate')(prop._default)
            setattr(self, '_' + name + '_value', value)
            if name not in property_values:
                ev = dict(type=name, new_value=value, old_value=value, mutation='set')
                events.append(ev)
        # Then process property values given at init time
        for name, value in property_values.items():  # is sorted by occurance in py36
            if name not in self.__properties__:
                if name in self.__attributes__:
                    raise AttributeError('%s.%s is an attribute, not a property' %
                                         (self._id, name))
                else:
                    raise AttributeError('%s does not have property %s.' %
                                         (self._id, name))
            if callable(value):
                self._comp_make_implicit_setter(name, value)
                continue
            value = getattr(self, '_' + name + '_validate')(value)
            setattr(self, '_' + name + '_value', value)
            ev = dict(type=name, new_value=value, old_value=value, mutation='set')
            events.append(ev)
        return events
    
    def _comp_make_implicit_setter(self, prop_name, func):
        setter_func = getattr(self, 'set_' + prop_name, None)
        if setter_func is None:
            t = '%s does not have a set_%s() action for property %s.'
            raise TypeError(t % (self._id, prop_name, prop_name)) 
        setter_reaction = lambda: setter_func(func())
        reaction = Reaction(self, setter_reaction, [])
        self.__anonymous_reactions.append(reaction)
    
    def _comp_init_reactions(self):
        # Instantiate reactions by referencing them, Connections are resolved now.
        # Implicit reactions need to be invoked to initialize connections.
        for name in self.__reactions__:
            reaction = getattr(self, name)
            if not reaction.is_explicit():
                ev = Dict(source=self, type='', label='')
                loop.add_reaction_event(reaction, ev)
        # Also invoke the anonymouse implicit reactions
        for reaction in self.__anonymous_reactions:
            if not reaction.is_explicit():
                ev = Dict(source=self, type='', label='')
                loop.add_reaction_event(reaction, ev)
    
    def _comp_init_events(self, prop_events):
        """ Initialize handlers and properties. You should only do this once,
        and only when using the object is initialized with _init_reactions=False.
        """
        
        if self.__pending_events is None:  # pragma: no cover
            return
        # Schedule a call to disable event capturing
        def stop_capturing():
            self.__pending_events = None
        loop.call_soon(stop_capturing)
        
        # Emit initial events for props
        for i in range(len(prop_events)):
            ev = prop_events[i]
            self.emit(ev['type'], ev)
    
    def __enter__(self):
        loop._activate_component(self)
        loop.call_soon(self.__check_not_active)
        return self
    
    def __exit__(self, type, value, traceback):
        loop._deactivate_component(self)
    
    def __check_not_active(self):
        # todo: disable this in production?
        active_components = loop.get_active_components()
        if self in active_components:
            raise RuntimeError('It seems that the event loop is processing '
                               'events while a Component is active. This has a '
                               'high risk on race conditions.')
    
    def init(self):
        """ Initializer method.
        
        This method can be overloaded when creating a custom class. It is
        called with this component as a context manager (making it the
        active component), and it gets the positional arguments passed to the
        Component constructor.
        """
        pass
    
    def __del__(self):
        if not self._disposed:
            loop.call_soon(self._dispose)
    
    def dispose(self):
        """ Use this to dispose of the object to prevent memory leaks.
        
        Make all subscribed reactions forget about this object, clear
        all references to subscribed reactions, disconnect all reactions
        defined on this object.
        """
        self._dispose()
    
    def _dispose(self):
        """ Distinguish between private and public method to allow disposing
        flexx.app.ProxyComponent without disposing its local version.
        """
        self._disposed = True
        if not this_is_js():
            logger.debug('Disposing Component %r' % self)
        for name, reactions in self.__handlers.items():
            for i in range(len(reactions)):
                reactions[i][1]._clear_component_refs(self)
            while len(reactions):
                reactions.pop()  # no list.clear on legacy py
        for i in range(len(self.__reactions__)):
            getattr(self, self.__reactions__[i]).dispose()
    
    def _registered_reactions_hook(self):
        """ Called when the reactions changed, can be implemented in subclasses.
        The original method returns a list of event types for which there is
        at least one registered reaction. Overloaded methods should return this
        list too.
        """
        used_event_types = []
        for key, reactions in self.__handlers.items():
            if len(reactions) > 0:
                used_event_types.append(key)
        return used_event_types
    
    def _register_reaction(self, event_type, reaction, force=False):
        # Register a reaction for the given event type. The type
        # can include a label, e.g. 'mouse_down:foo'.
        # This is called from Reaction objects at initialization and when
        # they reconnect (dynamism).
        type, _, label = event_type.partition(':')
        label = label or reaction._name
        reactions = self.__handlers.get(type, None)
        if reactions is None:  # i.e. type not in self.__handlers
            reactions = []
            self.__handlers[type] = reactions
            if not force:  # ! means force
                msg = ('Event type "{type}" does not exist on component {id}. ' +
                       'Use "!{type}" or "!xx.yy.{type}" to suppress this warning.')
                msg = msg.replace('{type}', type).replace('{id}', self._id)
                logger.warn(msg)
        
        # Insert reaction in good place (if not already in there) - sort as we add
        comp1 = label + '-' + reaction._id
        for i in range(len(reactions)):
            comp2 = reactions[i][0] + '-' + reactions[i][1]._id
            if comp1 < comp2:
                reactions.insert(i, (label, reaction))
                break
            elif comp1 == comp2:
                break  # already in there
        else:
            reactions.append((label, reaction))
        
        # Call hook to keep (subclasses of) the component up to date
        self._registered_reactions_hook()
        
        # Emit any pending events
        if self.__pending_events is not None:
            if not label.startswith('reconnect_'):
                events = self.__pending_events.get(type, [])
                for i in range(len(events)):
                    loop.add_reaction_event(reaction, events[i])
    
    def disconnect(self, type, reaction=None):
        """ Disconnect reactions. 
        
        Parameters:
            type (str): the type for which to disconnect any reactions.
                Can include the label to only disconnect reactions that
                were registered with that label.
            reaction (optional): the reaction object to disconnect. If given,
               only this reaction is removed.
        """
        # This is called from Reaction objects when they dispose and when
        # they reconnect (dynamism).
        type, _, label = type.partition(':')
        reactions = self.__handlers.get(type, ())
        for i in range(len(reactions)-1, -1, -1):
            entry = reactions[i]
            if not ((label and label != entry[0]) or
                    (reaction and reaction is not entry[1])):
                reactions.pop(i)
        self._registered_reactions_hook()
    
    def emit(self, type, info=None):
        """ Generate a new event and dispatch to all event reactions.
        
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
        # Push the event to the reactions (reactions use labels for dynamism)
        if self.__pending_events is not None:
            self.__pending_events.setdefault(ev.type, []).append(ev)
        # Register pending reactions
        # Reaction reconnections are applied directly; before a new event
        # occurs that the reaction might be subscribed to after the reconnect.
        reactions = self.__handlers.get(ev.type, ())
        for i in range(len(reactions)):
            label, reaction = reactions[i]
            if label.startswith('reconnect_'):
                index = int(label.split('_')[-1])
                reaction.reconnect(index)
            else:
                loop.add_reaction_event(reaction, ev)
        return ev
    
    def _mutate(self, prop_name, value, mutation='set', index=-1):
        """ Main mutator function. Each Component class will also have an
        auto-generated mutator function for each property.
        
        Arguments:
            prop_name (str): the name of the property being mutated.
            value: the new value, or the partial value for partial mutations.
            mutation (str): the kind of mutation to apply. Default is 'set'.
               Partial mutations can be applied by using 'insert', 'remove', or
               'replace'. If other than 'set', index must be specified,
               and >= 0. If 'remove', then value must be an int
               specifying the number of items to remove.
            index (int): the index at which to insert, remove or replace items.
            
        The 'replace' mutation also supports multidensional (numpy) arrays.
        In this case value can be an ndarray to patch the data with, and
        index a tuple of elements.
        """
        if not isinstance(prop_name, str):
            raise TypeError("_set_prop's first arg must be str, not %s" %
                             prop_name.__class__)
        if prop_name not in self.__properties__:
            cname = self.__class__.__name__
            raise AttributeError('%s object has no property %r' % (cname, prop_name))
        
        if loop.is_processing_actions() is False:
            raise AttributeError('Trying to mutate a property outside of an action.')
        
        # Prepare
        private_name = '_' + prop_name + '_value'
        validator_name = '_' + prop_name + '_validate'
        
        # Set / Emit
        value2 = value
        old = getattr(self, private_name)
        
        if mutation == 'set':
            # Normal setting of a property
            if this_is_js():  # pragma: no cover
                is_equal = old == value2
            elif hasattr(old, 'dtype') and hasattr(value2, 'dtype'):  # pragma: no cover
                import numpy as np
                is_equal = np.array_equal(old, value2)
            else:
                is_equal = type(old) == type(value2) and old == value2
            if not is_equal:
                value2 = getattr(self, validator_name)(value)
                setattr(self, private_name, value2)
                self.emit(prop_name,
                          dict(new_value=value2, old_value=old, mutation=mutation))
                return True
        else:
            # Array mutations - value is assumed to be a sequence, or int for 'remove'
            if index < 0:
                raise IndexError('For insert, remove, and replace mutations, '
                                 'the index must be >= 0.')
            ev = Dict()
            ev.objects = value
            ev.mutation = mutation
            ev.index = index
            mutate_array(old, ev)
            self.emit(prop_name, ev)
            return True
    
    def get_event_types(self):
        """ Get the known event types for this HasEvent object. Returns
        a list of event type names, for which there is a
        property/emitter or for which any reactions are registered.
        Sorted alphabetically.
        """
        types = list(self.__handlers)  # avoid using sorted (one less stdlib func)
        types.sort()
        return types
    
    def get_event_handlers(self, type):
        """ Get a list of reactions for the given event type. The order
        is the order in which events are handled: alphabetically by
        label.
        
        Parameters:
            type (str): the type of event to get reactions for. Should not
                include a label.
        
        """
        if not type:  # pragma: no cover - this is mostly since js allows missing args
            raise TypeError('get_event_handlers() missing "type" argument.')
        type, _, label = type.partition(':')
        if len(label):
            raise ValueError('The type given to get_event_handlers() '
                             'should not include a label.')
        reactions = self.__handlers.get(type, ())
        return [h[1] for h in reactions]

    def reaction(self, *connection_strings):
        """ Create a reaction by connecting a function to one or more events of
        this instance. Can also be used as a decorator. See the
        :func:`reaction <flexx.event.reaction>` decorator for more information.
        
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
        if (not connection_strings) or (len(connection_strings) == 1 and
                                        callable(connection_strings[0])):
            raise RuntimeError('Component.reaction() '
                                'needs one or more connection strings.')
        
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
            if not callable(func):  # pragma: no cover
                raise TypeError('Component.reaction() decorator requires a callable.')
            if looks_like_method(func):
                return ReactionDescriptor(func, connection_strings, self)
            else:
                return Reaction(self, func, connection_strings)
        
        if func is not None:
            return _react(func)
        else:
            return _react


def _mutate_array_py(array, ev):
    """ Logic to mutate an list-like or array-like property in-place, in Python.
    ev must be a dict with elements:
    * mutation: 'set', 'insert', 'remove' or 'replace'.
    * objects: the values to set/insert/replace, or the number of iterms to remove.
    * index: the (non-negative) index to insert/replace/remove at.
    """
    is_nd = hasattr(array, 'shape') and hasattr(array, 'dtype')
    mutation = ev['mutation']
    index = ev['index']
    objects = ev['objects']
    
    if is_nd:
        if mutation == 'set':  # pragma: no cover
            raise NotImplementedError('Cannot set numpy array in-place')
        elif mutation in ('extend', 'insert', 'remove'):  # pragma: no cover
            raise NotImplementedError('Cannot resize numpy arrays')
        elif mutation == 'replace':
            if isinstance(index, tuple):  # nd-replacement
                slices = tuple(slice(index[i], index[i] + objects.shape[i], 1)
                               for i in range(len(index)))
                array[slices] = objects
            else:
                array[index:index+len(objects)] = objects
    else:
        if mutation == 'set':
            array[:] = objects
        elif mutation == 'insert':
            array[index:index] = objects
        elif mutation == 'remove':
            assert isinstance(objects, int)  # objects must be a count in this case
            array[index:index+objects] = []
        elif mutation == 'replace':
            array[index:index+len(objects)] = objects
        else:
            raise NotImplementedError(mutation)


def _mutate_array_js(array, ev):  # pragma: no cover
    """ Logic to mutate an list-like or array-like property in-place, in JS.
    """
    is_nd = hasattr(array, 'shape') and hasattr(array, 'dtype')
    mutation = ev.mutation
    index = ev.index
    objects = ev.objects
    
    if is_nd is True:
        if mutation == 'set':
            raise NotImplementedError('Cannot set nd array in-place')
        elif mutation in ('extend', 'insert', 'remove'):
            raise NotImplementedError('Cannot resize nd arrays')
        elif mutation == 'replace':
            raise NotImplementedError('Cannot replace items in nd array')
    else:
        if mutation == 'set':
            array.splice(0, len(array), *objects)
        elif mutation == 'insert':
            array.splice(index, 0, *objects)
        elif mutation == 'remove':
            assert isinstance(objects, float)  # objects must be a count in this case
            array.splice(index, objects)
        elif mutation == 'replace':
            array.splice(index, len(objects), *objects)
        else:
            raise NotImplementedError(mutation)


mutate_array = _mutate_array_py
