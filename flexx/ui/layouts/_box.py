"""
The box layout classes provide a simple mechanism to horizontally
or vertically stack child widgets. The ``Box`` (and ``HBox`` and
``VBox``) are intended for laying out leaf content taking into account the
natural size of the child widgets. 

Example for Box layout:

.. UIExample:: 250
    
    from flexx import ui
    
    class Example(ui.Widget):
        def init(self):
            with ui.VBox:
                
                ui.Label(text='Flex 0 0 0')
                with ui.HBox(flex=0):
                    self.b1 = ui.Button(text='Hola', flex=0)
                    self.b2 = ui.Button(text='Hello world', flex=0)
                    self.b3 = ui.Button(text='Foo bar', flex=0)
                
                ui.Label(text='Flex 1 0 3')
                with ui.HBox(flex=0):
                    self.b1 = ui.Button(text='Hola', flex=1)
                    self.b2 = ui.Button(text='Hello world', flex=0)
                    self.b3 = ui.Button(text='Foo bar', flex=3)
                
                ui.Label(text='padding 10 (around layout)')
                with ui.HBox(flex=0, padding=10):
                    self.b1 = ui.Button(text='Hola', flex=1)
                    self.b2 = ui.Button(text='Hello world', flex=1)
                    self.b3 = ui.Button(text='Foo bar', flex=1)
                
                ui.Label(text='spacing 10 (inter-widget)')
                with ui.HBox(flex=0, spacing=10):
                    self.b1 = ui.Button(text='Hola', flex=1)
                    self.b2 = ui.Button(text='Hello world', flex=1)
                    self.b3 = ui.Button(text='Foo bar', flex=1)
                
                ui.Widget(flex=1)
                ui.Label(text='Note the spacer Widget above')


A similar example using a Split layout:

.. UIExample:: 250
    
    from flexx import ui
    
    class Example(ui.Widget):
        def init(self):
            with ui.VSplit():
                
                ui.Label(text='Flex 0 0 0', style='')
                with ui.HSplit(flex=0):
                    self.b1 = ui.Button(text='Hola', flex=0)
                    self.b2 = ui.Button(text='Hello world', flex=0)
                    self.b3 = ui.Button(text='Foo bar', flex=0)
                
                ui.Label(text='Flex 1 0 3')
                with ui.HSplit(flex=0):
                    self.b1 = ui.Button(text='Hola', flex=1)
                    self.b2 = ui.Button(text='Hello world', flex=0)
                    self.b3 = ui.Button(text='Foo bar', flex=3)
                
                ui.Label(text='spacing 10 (inter-widget)')
                with ui.HSplit(flex=0, spacing=20):
                    self.b1 = ui.Button(text='Hola', flex=1)
                    self.b2 = ui.Button(text='Hello world', flex=1)
                    self.b3 = ui.Button(text='Foo bar', flex=1)
                
                ui.Widget(flex=1)


Interactive Box layout example:

.. UIExample:: 200
    
    from flexx import ui, event
    
    class Example(ui.HBox):
        def init(self):
            self.b1 = ui.Button(text='Horizontal', flex=0)
            self.b2 = ui.Button(text='Vertical', flex=1)
            self.b3 = ui.Button(text='Horizontal reversed', flex=2)
            self.b4 = ui.Button(text='Vertical reversed', flex=3)
        
        class JS:
            
            @event.connect('b1.mouse_down')
            def _to_horizontal(self, *events):
                self.orientation = 'h'
            
            @event.connect('b2.mouse_down')
            def _to_vertical(self, *events):
                self.orientation = 'v'
            
            @event.connect('b3.mouse_down')
            def _to_horizontal_rev(self, *events):
                self.orientation = 'hr'
            
            @event.connect('b4.mouse_down')
            def _to_vertical_r(self, *events):
                self.orientation = 'vr'


A classic high level layout:


.. UIExample:: 300

    from flexx import ui
    
    
    class Content(ui.Widget):
        def init(self):
                # Here we use Box layout, because we care about natural size
                
                with ui.HBox():
                    ui.Widget(flex=1)  # spacer
                    ui.Button(text='hello')
                    ui.Widget(flex=1)  # spacer
    
    
    class SideWidget(ui.Label):
        CSS = '.flx-SideWidget {background: #aaf; border: 2px solid black;}'
    
    
    class Example(ui.Widget):
    
        def init(self):
            # Here we use Split layout, because we define high-level layout
            
            with ui.VSplit():
                SideWidget(text='Header', flex=0, base_size=100)
                with ui.HSplit(flex=1):
                    SideWidget(text='Left', flex=0, base_size=100)
                    Content(flex=1)
                    SideWidget(text='Right', flex=0, base_size=100)
                SideWidget(text='Bottom', flex=0, base_size=100)

"""

from ... import event
from ...pyscript import RawJS
from . import Layout


# _phosphor_boxpanel = RawJS("flexx.require('phosphor/lib/ui/boxpanel')")


class OrientationProp(event.Property):
    """ A property that represents a pair of float values, which can also be
    set using a scalar.
    """
    
    _default = 'h'
    
    def _validate(self, v):
        if isinstance(v, str):
            v = v.lower().replace('-', '')
        v = {'horizontal': 'h', 0: 'h', 'lefttoright': 'h',
             'vertical': 'v', 1: 'v', 'toptobottom': 'v',
             'righttoleft': 'hr', 'bottomtotop': 'vr'}.get(v, v)
        if v not in ('h', 'v', 'hr', 'vr'):
            raise ValueError('%s.orientation got unknown value %r' % (self.id, v))
        return v


class Box(Layout):
    """ Layout to distribute space for widgets horizontally or vertically. 
    
    This layout implements CSS flexbox. The reference size of each child
    widget is based on its natural size (e.g. a button's text). Each widget
    gets at least this space (if possible), and the remaining space is 
    distributed among the widgets corresponding to their flex values. This
    process is subject to the constrains of the widgets minimum and maximum
    sizes (as set via style/CSS).
    
    The Split class provides a similar layout, but does not take natural size
    into account and is therefore more suited for high-level layout.
    
    Also see the VBox and HBox convenience classes.
    """
    
    _DEFAULT_ORIENTATION = 'h'
    
    CSS = """
    .flx-hbox, .flx-vbox, .flx-hboxr, .flx-vboxr {
        display: -webkit-flex;
        display: -ms-flexbox;  /* IE 10 */
        display: -ms-flex;     /* IE 11 */
        display: -moz-flex;
        display: flex;
        
        /* How space is divided when all flex-factors are 0:
           start, end, center, space-between, space-around */
        -webkit-justify-content: space-around;
        -ms-justify-content: space-around;
        -moz-justify-content: space-around;
        justify-content: space-around;
        
        /* How items are aligned in the other direction:
           center, stretch, baseline */
        -webkit-align-items: stretch;  
        -ms-align-items: stretch;
        -moz-align-items: stretch;
        align-items: stretch;
    }
    
    .flx-hbox {
        -webkit-flex-flow: row; -ms-flex-flow: row; -moz-flex-flow: row; flex-flow: row;
        width: 100%;
    }
    .flx-vbox {
        -webkit-flex-flow: column;
        -ms-flex-flow: column;
        -moz-flex-flow: column;
        flex-flow: column;
        height: 100%; width: 100%;
    }
    .flx-hboxr {
        -webkit-flex-flow: row-reverse;
        -ms-flex-flow: row-reverse;
        -moz-flex-flow: row-reverse;
        flex-flow: row-reverse;
        width: 100%;
    }
    .flx-vboxr {
        -webkit-flex-flow: column-reverse;
        -ms-flex-flow: column-reverse;
        -moz-flex-flow: column-reverse;
        flex-flow: column-reverse;
        height: 100%; width: 100%;
    }
    
    /* Make child widgets (and layouts) size correctly */
    .flx-hbox > .flx-Widget, .flx-hboxr > .flx-Widget {
        height: auto;
        width: auto;
    }
    .flx-vbox > .flx-Widget, .flx-vboxr > .flx-Widget {
        width: auto;
        height: auto;
    }
    
    /* If a boxLayout is in a compound widget, we need to make that widget
       a flex container (done with JS in Widget class), and scale here */
    .flx-Widget > .flx-Box {
        flex-grow: 1;
        flex-shrink: 1;
    }
    """
    
    spacing = event.FloatProp(5, settable=True, doc="""
        The space between two child elements (in pixels)
        """)
    
    padding = event.FloatProp(1, settable=True, doc="""
        The empty space around the layout (in pixels).
        """)
    
    orientation = OrientationProp(settable=True, doc="""
        The orientation of the child widgets. 'h' or 'v' for horizontal and
        vertical, or their reversed variants 'hr' and 'vr'. Settable with
        values: 0, 1, 'h', 'v', 'hr', 'vr', 'horizontal', 'vertical',
        'left-to-right', 'right-to-left', 'top-to-bottom', 'bottom-to-top'.
        """)
    
    def __init__(self, *args, **kwargs):
        kwargs['orientation'] = kwargs.get('orientation', self._DEFAULT_ORIENTATION)
        super().__init__(*args, **kwargs)
    
    @event.reaction('orientation', 'children', 'children*.flex')
    def __set_flexes(self, *events):
        ori = self.orientation
        i = 0 if ori in (0, 'h', 'hr') else 1
        for widget in self.children:
            self._applyBoxStyle(widget.outernode, 'flex-grow', widget.flex[i])
            self._applyBoxStyle(widget.outernode, 'flex-shrink',
                                widget.flex[i] or 1)  # default value is 1
        for widget in self.children:
            widget.check_real_size()
    
    @event.reaction('spacing', 'orientation', 'children')
    def __spacing_changed(self, *events):
        ori = self.orientation
        children_events = [ev for ev in events if ev.type == 'children']
        old_children = children_events[0].old_value if children_events else []
        children = self.children
        # Reset
        for child in children:
            child.outernode.style['margin-top'] = ''
            child.outernode.style['margin-left'] = ''
        for child in old_children:
            child.outernode.style['margin-top'] = ''
            child.outernode.style['margin-left'] = ''
        # Set
        margin = 'margin-top' if ori in (1, 'v', 'vr') else 'margin-left'
        if children.length:
            if ori in ('vr', 'hr'):
                children[-1].outernode.style[margin] = '0px'
                for child in children[:-1]:
                    child.outernode.style[margin] = self.spacing + 'px'
            else:
                children[0].outernode.style[margin] = '0px'
                for child in children[1:]:
                    child.outernode.style[margin] = self.spacing + 'px'
        for widget in children:
            widget.check_real_size()
    
    @event.reaction('padding')
    def __padding_changed(self, *events):
        self.outernode.style['padding'] = self.padding + 'px'
        for widget in self.children:
            widget.check_real_size()
    
    @event.reaction('orientation')
    def __orientation_changed(self, *events):
        ori = self.orientation
        for name in ('hbox', 'vbox', 'hboxr', 'vboxr'):
            self.outernode.classList.remove('flx-'+name)
        if ori == 0 or ori == 'h':
            self.outernode.classList.add('flx-hbox')
        elif ori == 1 or ori == 'v':
            self.outernode.classList.add('flx-vbox')
        elif ori == 'hr':
            self.outernode.classList.add('flx-hboxr')
        elif ori == 'vr':
            self.outernode.classList.add('flx-vboxr')
        else:
            raise ValueError('Invalid box orientation: ' + ori)
        for widget in self.children:
            widget.check_real_size()
    
    def _applyBoxStyle(self, e, sty, value):
        for prefix in ['-webkit-', '-ms-', '-moz-', '']:
            e.style[prefix + sty] = value


class HBox(Box):
    """ Horizontal Box layout.
    """
    _DEFAULT_ORIENTATION = 'h'


class VBox(Box):
    """ Vertical Box layout.
    """
    _DEFAULT_ORIENTATION = 'v'
