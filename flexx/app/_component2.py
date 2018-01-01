"""
Implementation of the app Component classes (LocalComponent,
ProxyComponent, StubComponent), which form the basis for the
PyComponent and JsComponent classes (and their proxies).
"""

import sys

from ..pyscript import window, JSString, this_is_js

from .. import event

from ..event import Component, loop, Dict
from ..event._component import (with_metaclass, ComponentMeta)

from ..event._property import Property
from ..event._emitter import EmitterDescriptor
from ..event._action import ActionDescriptor
from ..event._js import create_js_component_class

from ._asset import get_mod_name
from . import logger


# The clientcore module is a PyScript module that forms the core of the
# client-side of Flexx. We import the serializer instance, and can use
# that name in both Python and JS. Of course, in JS it's just the
# corresponding instance from the module that's being used.
# By using something from clientcore in JS here, we make clientcore a
# dependency of the the current module.
from ._clientcore import serializer, bsdf

manager = None  # Set by __init__ to prevent circular dependencies


def make_proxy_action(action):
    # Note: the flx_prefixes are picked up by the code in flexx.event that
    # compiles component classes, so it can fix /insert the name for JS.
    flx_name = action._name
    def flx_proxy_action(self, *args):
        self._proxy_action(flx_name, *args)
    flx_proxy_action.__doc__ = action.__doc__  # todo: or action._doc?
    return flx_proxy_action  # ActionDescriptor(flx_proxy_action, flx_name, '')


def make_proxy_emitter(emitter):
    # Note: the flx_prefixes are picked up by the code in flexx.event that
    # compiles component classes, so it can fix /insert the name for JS.
    flx_name = emitter._name
    def flx_proxy_emitter(self, *args):
        self._proxy_emitter(flx_name, *args)
    flx_proxy_emitter.__doc__ = emitter.__doc__  # todo: or emitter._doc?
    return flx_proxy_emitter  # EmitterDescriptor(flx_proxy_emitter, flx_name, '')


def get_component_classes():
    """ Get a list of all known PyComponent and JsComponent subclasses.
    """
    return [c for c in AppComponentMeta.CLASSES]


def meta_repr(cls):
    """ A repr function to provide some context on the purpose of a class.
    """
    if issubclass(cls, PyComponent):
        prefix = 'PyComponent class'
    elif issubclass(cls, PyComponent.JS):
        prefix = 'proxy PyComponent class for JS '
    elif issubclass(cls, JsComponent):
        prefix = 'proxy JsComponent class'
    elif issubclass(cls, JsComponent.JS):
        prefix = 'JsComponent class for JS'
    else:
        prefix = 'class'
    return "<%s '%s.%s'>" % (prefix, cls.__module__, cls.__name__)


class LocalProperty(Property):
    """ A generic property that is only present at the local side of
    the component, i.e. not at the proxy. Intended for properties that
    the other side should not care about, and/or for wich syncing would be
    problematic, e.g. for performance or because it contains components
    that we want to keep local.
    """


class ComponentMetaJS(ComponentMeta):
    """ Meta class for autogenerated classes intended for JavaScript:
    Proxy PyComponent and local JsComponents.
    """
    
    __repr__ = meta_repr
    
    def __init__(cls, name, *args):
        name = name.encode() if sys.version_info[0] == 2 else name
        return super().__init__(name, *args)


class AppComponentMeta(ComponentMeta):
    """ Meta class for PyComponent and JsComponent
    that generate a matching class for JS.
    """
    
    # Keep track of all subclasses
    CLASSES = []
    
    __repr__ = meta_repr
    
    def _init_hook1(cls, cls_name, bases, dct):
        
        # cls is the class to be
        # cls.__dict__ is its current dict, which may contain inherited items
        # dct is the dict represented by exactly this class (no inheritance)
        
        # Get CSS from the class now
        CSS = dct.get('CSS', '')
        
        # Create corresponding class for JS
        if issubclass(cls, LocalComponent):
            cls._make_js_proxy_class(cls_name, bases, dct)
        elif issubclass(cls, ProxyComponent):
            cls._make_js_local_class(cls_name, bases, dct)
        else:  # pragma: no cover
            raise TypeError('Expected class to inherit from '
                            'LocalComponent or ProxyComponent.')
        
        # Write __jsmodule__; an optimization for our module/asset system
        cls.__jsmodule__ = get_mod_name(sys.modules[cls.__module__])
        cls.JS.__jsmodule__ = cls.__jsmodule__  # need it in JS too
        
        # Set CSS
        cls.CSS = CSS
        try:
            delattr(cls.JS, 'CSS')
        except AttributeError:
            pass
    
    def _init_hook2(cls, cls_name, bases, dct):
        
        # Set __proxy_properties__
        if issubclass(cls, LocalComponent):
            cls.__proxy_properties__ = cls.JS.__properties__
        else:
            cls.JS.__proxy_properties__ = cls.__properties__
        
        # Set JS on the JS class
        cls.JS.CODE = cls._get_js()
        
        # Register this class. The classes in this list will be automatically
        # "pushed to JS" in a JIT fashion. We have to make sure that we include
        # the code for base classes not in this list, which we do in _get_js().
        AppComponentMeta.CLASSES.append(cls)
    
    def _make_js_proxy_class(cls, cls_name, bases, dct):
        
        for c in bases:
            assert not issubclass(cls, ProxyComponent)
        
        # Fix inheritance for JS variant
        jsbases = [getattr(b, 'JS') for b in cls.__bases__ if hasattr(b, 'JS')]
        if not jsbases:
            jsbases.append(ProxyComponent)
        jsdict = {}
        
        # Copy properties from this class to the JS proxy class.
        # in Python 3.6 we iterate in the order in which the items are defined,
        for name, val in dct.items():
            if name.startswith('__') and name.endswith('__'):
                continue
            elif isinstance(val, LocalProperty):
                pass  # do not copy over
            elif isinstance(val, Property):
                jsdict[name] = val  # properties are the same
            elif isinstance(val, EmitterDescriptor):
                jsdict[name] = make_proxy_emitter(val)  # proxy emitter
            elif isinstance(val, ActionDescriptor):
                jsdict[name] = make_proxy_action(val)  # proxy actions
            else:
                pass  # no reactions/functions/class attributes on the proxy side
        
        # Create JS class
        cls.JS = ComponentMetaJS(cls_name, tuple(jsbases), jsdict)
    
    def _make_js_local_class(cls, cls_name, bases, dct):
        
        for c in bases:
            assert not issubclass(cls, LocalComponent)
        
        # Fix inheritance for JS variant
        jsbases = [getattr(b, 'JS') for b in cls.__bases__ if hasattr(b, 'JS')]
        if not jsbases:
            jsbases.append(LocalComponent)
        jsdict = {}
        
        # Names that should stay in Python in addition to magic methods
        py_only = ['_repr_html_']
        
        # Copy properties from this class to the JS proxy class.
        # in Python 3.6 we iterate in the order in which the items are defined,
        for name, val in list(dct.items()):
            if name in py_only or name.startswith('__') and name.endswith('__'):
                if name not in ('__init__'):
                    continue
            if (isinstance(val, Property) or (callable(val) and
                  name.endswith('_validate'))):
                jsdict[name] = val  # properties are the same
                if isinstance(val, LocalProperty):
                    delattr(cls, name)
                    dct.pop(name, None)
            elif isinstance(val, EmitterDescriptor):
                # JS part gets the proper emitter, Py side gets a proxy
                jsdict[name] = val
                setattr(cls, name, make_proxy_emitter(val))
            elif isinstance(val, ActionDescriptor):
                # JS part gets the proper action, Py side gets a proxy
                jsdict[name] = val
                setattr(cls, name, make_proxy_action(val))
            else:
                # Move attribute from the Py class to the JS class
                jsdict[name] = val
                delattr(cls, name)
                dct.pop(name, None)  # is this necessary? 
        
        # Create JS class
        cls.JS = ComponentMetaJS(cls_name, tuple(jsbases), jsdict)
    
    def _get_js(cls):
        """ Get source code for this class plus the meta info about the code.
        """
        # Since classes are defined in a module, we can safely name the classes
        # by their plain name. 
        # But flexx.classes.X remains the "official" 
        # namespace, so that things work easlily accross modules, and we can
        # even re-define classes (e.g. in the notebook).
        # todo: did getting rid of flexx.classes break notebook interactivity?
        cls_name = cls.__name__
        base_class = cls.JS.mro()[1]
        base_class_name = '%s.prototype' % base_class.__name__
        code = []
        
        # Add this class
        c = create_js_component_class(cls.JS, cls_name, base_class_name)
        meta = c.meta
        code.append(c)
        # code.append(c.replace('var %s =' % cls_name,
        #                   'var %s = flexx.classes.%s =' % (cls_name, cls_name), 1))
        
        # Add JS version of the base classes - but only once
        if cls.__name__ == 'JsComponent':
            c = cls._get_js_of_base_classes()
            for k in ['vars_unknown', 'vars_global', 'std_functions', 'std_methods']:
                meta[k].update(c.meta[k])
            code.insert(0, c)
        
        # Return with meta info
        js = JSString('\n'.join(code))
        js.meta = meta
        return js
    
    def _get_js_of_base_classes(cls):
        """ Get JS for BaseAppComponent, LocalComponent, and ProxyComponent.
        """
        c1 = create_js_component_class(BaseAppComponent, 'BaseAppComponent',
                                       'Component.prototype')
        c2 = create_js_component_class(LocalComponent, 'LocalComponent',
                                       'BaseAppComponent.prototype')
        c3 = create_js_component_class(ProxyComponent, 'ProxyComponent',
                                       'BaseAppComponent.prototype')
        c4 = create_js_component_class(StubComponent, 'StubComponent',
                                       'BaseAppComponent.prototype')
        meta = c1.meta
        for k in ['vars_unknown', 'vars_global', 'std_functions', 'std_methods']:
            for c in (c2, c3, c4):
                meta[k].update(c.meta[k])
        js = JSString('\n'.join([c1, c2, c3, c4]))
        js.meta = meta
        return js


class BaseAppComponent(Component):
    """ Abstract class for Component classes that can be "shared" between
    Python and JavaScript. The concrete implementations are:
    
    * The PyComponent class, which operates in Python, but has a proxy
      object in JavaSript to which properties are synced and from which actions
      can be invoked.
    * The JsComponent class, which operates in JavaScript, but can have a proxy
      object in Python to which properties are synced and from which actions
      can be invoked.
    * The StubComponent class, which represents a component class that is
      somewhere else, perhaps in another session. It does not have any
      properties, nor actions. But it can be "moved around".
    """
    
    session = event.Attribute(doc="The session to which this component belongs. " + 
                                  "It's id is unique within the session.")
    
    uid = event.Attribute(doc="A unique identifier for this component; " + 
                              "a combination of the session and component id's.")

    def _comp_init_app_component(self, property_values):
        # Pop special attribute
        property_values.pop('flx_is_app', None)
        # Pop and apply id if given
        custom_id = property_values.pop('flx_id', None)
        # Pop session or derive from active component
        self._session = None
        session = property_values.pop('flx_session', None)
        if session is not None:
            self._session = session
        else:
            active = loop.get_active_component()
            if active is not None:
                self._session = active._session
            else:
                if not this_is_js():
                    self._session = manager.get_default_session()
        
        # Register this component with the session (sets _id and _uid)
        if self._session is None:
            raise RuntimeError('%s needs a session!' % (custom_id or self._id))
        self._session._register_component(self, custom_id)
        
        # Return whether this instance was instantiated locally
        return custom_id is None


class LocalComponent(BaseAppComponent):
    """
    Base class for PyComponent in Python and JsComponent in JavaScript.
    """
    
    def _comp_init_property_values(self, property_values):
        # This is a good time to register with the session, and
        # instantiate the proxy class. Property values have been set at this
        # point, but init() has not yet been called.
        
        # Keep track of what events are registered at the proxy
        self.__event_types_at_proxy = []
        
        # Init more
        self._comp_init_app_component(property_values)  # pops items 
        
        # Pop whether this local instance has a proxy at the other side
        self._has_proxy = property_values.pop('flx_has_proxy', False)
        
        # Call original method
        prop_events = super()._comp_init_property_values(property_values)
        
        if this_is_js():
            # This is a local JsComponent in JavaScript
            self._event_listeners = []
        else:
            # This is a local PyComponent in Python
            # A PyComponent always has a corresponding proxy in JS
            self._ensure_proxy_instance(False)
        
        return prop_events
    
    def _ensure_proxy_instance(self, include_props=True):
        """ Make the other end instantiate a proxy if necessary. This is e.g.
        called by the BSDF serializer when a LocalComponent gets serialized.
        
        A PyComponent always has a Proxy component, and we should not
        dispose or delete it until the local component is disposed.
        
        A JsComponent may be instantiated (as its proxy) from Python, in which
        case we receive the flx_has_proxy kwarg. Still, Python can "loose" the
        proxy class. To ensure that it exists in Python when needed, the BSDF
        serializer will ensure it (by calling this method) when it gets
        serialized.
        
        In certain cases, it might be that the other end *does* have a proxy
        while this end's _has_proxy is False. In that case the INSTANTIATE
        command is send, but when handled, will be a no-op.
        
        In certain cases, it might be that the other end just lost its
        reference; this end's _has_proxy is True, and a new reference to this
        component will fail to resolve. This is countered by keeping hold
        of JsComponent proxy classes for at least one roundtrip (upon
        initialization as well as disposal).
        """
        if self._has_proxy is False and self._disposed is False:
            if self._session.status > 0:
                props = {}
                if include_props:
                    for name in self.__proxy_properties__:
                        props[name] = getattr(self, name)
                self._session.send_command('INSTANTIATE', self.__jsmodule__,
                                           self.__class__.__name__,
                                           self._id, [], props)
                self._has_proxy = True
    
    def emit(self, type, info=None):
        # Overload emit() to send events to the proxy object at the other end
        ev = super().emit(type, info)
        isprop = type in self.__proxy_properties__
        if self._has_proxy is True and self._session.status > 0:
            # implicit: and self._disposed is False:
            if isprop or type in self.__event_types_at_proxy:
                self._session.send_command('INVOKE', self._id,
                                           '_emit_at_proxy', [ev])
    
    def _dispose(self):
        # Let proxy side know that we no longer exist, and that it should
        # dispose too. Send regardless of whether we have a proxy!
        was_disposed = self._disposed
        super()._dispose()
        self._has_proxy = False  # because we will tell it to dispose
        if was_disposed is False and self._session is not None:
            self._session._unregister_component(self)
            if self._session.status > 0:
                self._session.send_command('DISPOSE', self._id)

    def _flx_set_has_proxy(self, has_proxy):
        self._has_proxy = has_proxy
    
    def _flx_set_event_types_at_proxy(self, event_types):
        self.__event_types_at_proxy = event_types
    
    # todo: probably remove this, we have actions now!
    # def call_js(self, call):
    #     raise RuntimeError('call_js() is deprecated; '
    #                        'use actions or session.send_command("INVOKE", ..).')
    

class ProxyComponent(BaseAppComponent):
    """
    Base class for JSComponent in Python and PyComponent in JavaScript.
    """
    
    def __init__(self, *init_args, **kwargs):
        # Need to overload this to handle init_args
        
        if this_is_js():
            # This is a proxy PyComponent in JavaScript.
            # Always instantiated via an INSTANTIATE command from Python.
            assert len(init_args) == 0
            if 'flx_id' not in kwargs:
                raise RuntimeError('Cannot instantiate a PyComponent from JS.')
            super().__init__(**kwargs)
        else:
            # This is a proxy JsComponent in Python.
            # Can be instantiated in Python, 
            self._flx_init_args = init_args
            super().__init__(**kwargs)
    
    def _comp_init_property_values(self, property_values):
        
        # Init more
        local_inst = self._comp_init_app_component(property_values)  # pops items 
        
        # Call original method, only set props if this is instantiated "by the local"
        props2set = {} if local_inst else property_values
        prop_events = super()._comp_init_property_values(props2set)  # noqa - we return [] 
        
        if this_is_js():
            # This is a proxy PyComponent in JavaScript
            assert len(property_values.keys()) == 0
        else:
            # This is a proxy JsComponent in Python
            # Instantiate JavaScript version of this class
            if local_inst is True:  # i.e. only if Python "instantiated" it
                property_values['flx_has_proxy'] = True
                active_components = [c for c in loop.get_active_components()
                                     if isinstance(c, (PyComponent, JsComponent))]
                self._session.send_command('INSTANTIATE', self.__jsmodule__,
                                           self.__class__.__name__, self._id,
                                           self._flx_init_args, property_values,
                                           active_components)
            del self._flx_init_args
        
        return []  # prop_events - Proxy class does not emit events by itself
    
    def _proxy_action(self, name, *args, **kwargs):
        """ To invoke actions on the real object.
        """
        assert not kwargs
        # if self._session.status > 0, mmm, or rather error?
        self._session.send_command('INVOKE', self._id, name, args)
    
    def _proxy_emitter(self, name, *args, **kwargs):
        """ To handle use of placeholder emitters.
        """
        # todo: I am not sure yet whether to allow or disallow it. We disallow now;
        # we can always INVOKE the emitter at the other side if that proves needed
        if this_is_js():
            logger.error('Cannot use emitters of a PyComponent in JS.')
        else:
            logger.error('Cannot use emitters of a JsComponent in Py.')
        
    def _mutate(self, *args, **kwargs):  # pragma: no cover
        """ Disable mutations on the proxy class.
        """
        raise RuntimeError('Cannot mutate properties from a proxy class.')
        # Reference objects to get them collected into the JS variant of this
        # module. Do it here, in a place where it wont hurt.
        serializer  # to bring in _clientcore as a way of bootstrapping
        BsdfComponentExtension
    
    def _registered_reactions_hook(self):
        """ Keep the local component informed about what event types this proxy
        is interested in. This way, the trafic can be minimized, e.g. not send
        mouse move events if they're not used anyway.
        """
        event_types = super()._registered_reactions_hook()
        try:
            if self._disposed is False and self._session.status > 0:
                self._session.send_command('INVOKE', self._id,
                                           '_flx_set_event_types_at_proxy',
                                           [event_types])
        finally:
            return event_types
    
    @event.action
    def _emit_at_proxy(self, ev):
        """ Action used by the local component to push an event to the proxy
        component. If the event represents a property-update, the mutation
        is applied, otherwise the event is emitted here.
        """
        if not this_is_js():
            ev = Dict(ev)
        if ev.type in self.__properties__ and hasattr(ev, 'mutation'):
            # Mutate the property - this will cause an emit
            if ev.mutation == 'set':
                super()._mutate(ev.type, ev.new_value)
            else:
                super()._mutate(ev.type, ev.objects, ev.mutation, ev.index)
        else:
            self.emit(ev.type, ev)
    
    def dispose(self):
        if this_is_js():
            # The server is leading ...
            raise RuntimeError('Cannot dispose a PyComponent from JS.')
        else:
            # Disposing a JsComponent from JS is like invoking an action;
            # we don't actually dispose ourselves just yet.
            if self._session.status > 0:
                self._session.send_command('INVOKE', self._id, 'dispose', [])
            else:
                super().dispose()
    
    def _dispose(self):
        # This gets called by the session upon a DISPOSE command,
        # or on Python from __delete__ (via call_soon).
        was_disposed = self._disposed
        super()._dispose()
        if was_disposed is False and self._session is not None:
            self._session._unregister_component(self)
            if self._session.status > 0:
                # Let other side know that we no longer exist.
                self._session.send_command('INVOKE', self._id,
                                           '_flx_set_has_proxy', [False])


class StubComponent(BaseAppComponent):
    """
    Class to represent stub proxy components to take the place of components
    that do not belong to the current session, or that are may not exist 
    for whatever reason. These objects cannot really be used, but they can
    be moved around.
    """
    
    def __init__(self, session, id):
        super().__init__()
        self._session = session
        self._id = id
        self._uid = session.id + '_' + id
    
    def __repr__(self):
        return ("<StubComponent for '%s' in session '%s' at 0x%x>" %
                (self._id, self._session.id, id(self)))


# LocalComponent and ProxyComponent need __jsmodule__, but they do not
# participate in the AppComponentMeta class, so we add it here.
LocalComponent.__jsmodule__ = __name__
ProxyComponent.__jsmodule__ = __name__
StubComponent.__jsmodule__ = __name__


class PyComponent(with_metaclass(AppComponentMeta, LocalComponent)):
    """ Base component class that operates in Python, but is accessible
    in JavaScript, where its properties and events can be observed,
    and actions can be invoked.
    
    PyComponents can only be instantiated in Python, and always have
    a corresponding proxy object in JS. PyComponents can be disposed only
    from Python. Disposal also happens if the Python garbage collector
    collects a PyComponent.
    
    """
    
    # The meta class generates a PyComponent proxy class for JS.
    
    def __repr__(self):
        d = ' (disposed)' if self._disposed else ''
        return "<PyComponent '%s'%s at 0x%x>" % (self._id, d, id(self))


class JsComponent(with_metaclass(AppComponentMeta, ProxyComponent)):
    """ Base component class that operates in JavaScript, but is accessible
    in Python, where its properties and events can be observed,
    and actions can be invoked.
    
    JsComponents can be instantiated from both JavaScript and Python. A
    corresponding proxy component is not necessarily present in Python. It
    is created automatically when needed (e.g. when referenced by a property).
    A JsComponent can be explicitly disposed from both Python and JavaScript.
    When the Python garbage collector collects a JsComponent (or really, the
    proxy thereof), only the Python side proxy is disposed; the JsComponent
    in JS itself will be unaffected.
    
    """
    
    # The meta class will generate a JsComponent local class for JS
    # and move all props, actions, etc. to it.
    
    def __repr__(self):
        d = ' (disposed)' if self._disposed else ''
        return "<JsComponent '%s'%s at 0x%x>" % (self._id, d, id(self))

    def _addEventListener(self, node, type, callback, capture=False):
        """ Register events with DOM nodes, to be automatically cleaned up
        when this object is disposed.
        """
        node.addEventListener(type, callback, capture)
        self._event_listeners.append((node, type, callback, capture))
    
    def _dispose(self):
        super()._dispose()
        while len(self._event_listeners) > 0:
            try:
                node, type, callback, capture = self._event_listeners.pop()
                node.removeEventListener(type, callback, capture)
            except Exception as err:
                print(err)


class BsdfComponentExtension(bsdf.Extension):
    """ A BSDF extension to encode flexx.app Component objects based on their
    session id and component id.
    """
    
    name = 'flexx.app.component'
    cls = BaseAppComponent  # PyComponent, JsComponent, StubComponent
    
    def match(self, s, c):
        # This is actually the default behavior, but added for completenes
        return isinstance(c, self.cls)
    
    def encode(self, s, c):
        if isinstance(c, PyComponent):  # i.e. LocalComponent in Python
            c._ensure_proxy_instance()
        return dict(session_id=c._session.id, id=c._id)
    
    def decode(self, s, d):
        c = None
        session = manager.get_session_by_id(d['session_id'])
        if session is None:
            # object from other session
            session = object()
            session.id = d['session_id']
            c = StubComponent(session, d['id'])
        else:
            c = session.get_component_instance(d['id'])
            if c is None:  # This should probably not happen
                logger.warn('Using stub component for %s.' % d['id'])
                c = StubComponent(session, d['id'])
            else:
                # Keep it alive for a bit
                session.keep_alive(c)
        return c
    
    # The name and below methods get collected to produce a JS BSDF extension
    
    def match_js(self, s, c):  # pragma: no cover
        return isinstance(c, BaseAppComponent)

    def encode_js(self, s, c):  # pragma: no cover
        if isinstance(c, JsComponent):  # i.e. LocalComponent in JS
            c._ensure_proxy_instance()
        return dict(session_id=c._session.id, id=c._id)
    
    def decode_js(self, s, d):  # pragma: no cover
        c = None
        session = window.flexx.sessions.get(d['session_id'], None)
        if session is None:
            session = dict(id=d['session_id'])
            c = StubComponent(session, d['id'])
        else:
            c = session.get_component_instance(d['id'])
            if c is None:
                logger.warn('Using stub component for %s.' % d['id'])
                c = StubComponent(session, d['id'])
        return c


# todo: can the mechanism for defining BSDF extensions be simplified?
# Add BSDF extension for serializing components. The JS variant of the
# serializer is added by referencing the extension is JS code.
serializer.add_extension(BsdfComponentExtension)
