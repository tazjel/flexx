"""
Test component properties.
"""

from flexx.util.testing import run_tests_if_main, skipif, skip, raises
from flexx.event._both_tester import run_in_both

from flexx import event

loop = event.loop

def this_is_js():
    return False


class MyObject(event.Component):
    
    # Props to test basic stuff
    foo = event.AnyProp(6, settable=True)
    bar = event.StringProp('xx')  # not settable
    
    # Props to test array mutations
    eggs = event.ListProp([], settable=True)
    # todo: good defaults!  eggs2 = event.ListProp()
    eggs3 = event.ListProp([3, 4])
    
    # All kinds of props
    anyprop = event.AnyProp(None, 'can be anything', settable=True)
    boolprop = event.BoolProp(False, settable=True)
    intprop = event.IntProp(0, settable=True)
    floatprop = event.FloatProp(0, settable=True)
    stringprop = event.StringProp('', settable=True)
    tupleprop = event.TupleProp((), settable=True)
    listprop = event.ListProp([], settable=True)
    componentprop = event.ComponentProp(None, settable=True)  # can be None
    # nullprop = event.NullProp(None, settable=True)
    # eitherprop = event.EitherProp(event.IntProp, event.NoneProp)


@run_in_both(MyObject)
def test_property_setting():
    """
    6
    xx
    6
    3.2
    fail ok
    xx
    """
    
    m = MyObject()
    print(m.foo)
    print(m.bar)
    
    m.set_foo(3.2)
    print(m.foo)
    loop.iter()
    print(m.foo)
    
    try:
        m.set_bar('yy')
    except AttributeError:
        print('fail ok')  # py
    except TypeError:
        print('fail ok')  # js
    print(m.bar)



@run_in_both(MyObject)
def test_property_mutating():
    """
    cannot mutate
    6
    9
    """
    m = MyObject()
    
    try:
        m._mutate_foo(9)
    except AttributeError:
        print('cannot mutate')
    
    print(m.foo)
    
    # Hack
    loop._processing_action = True
    m._mutate_foo(9)
    print(m.foo)


# todo: enable for JS once we can do keyword args in pyscript!
@run_in_both(MyObject, js=False)
def test_property_defaults():
    """
    6
    xx
    9
    xx
    fail ok
    end
    """
    
    m = MyObject(foo=9)
    print(m.foo)
    print(m.bar)
    
    loop.iter()
    print(m.foo)
    print(m.bar)
    
    try:
        MyObject(bar='yy')
    except AttributeError:
        print('fail ok')  # py and js
    print('end')


@run_in_both(MyObject) 
def test_property_list_init():
    """
    []
    [3, 4]
    """
    m = MyObject()
    print(m.eggs)
    print(m.eggs3)
    
    # todo: property defaults
    # print(m.eggs2)
    
    # todo: pyscript kwargs!
    # m = MyObject(eggs=[7,8,9])
    # loop.iter()
    # print(m.eggs)


@run_in_both(MyObject) 
def test_property_list_mutate():
    """
    []
    [1, 2, 3, 4, 5, 6, 7, 8]
    [1, 2, 3, 44, 55, 66, 7, 8]
    [1, 2, 3, 7, 8]
    """
    m = MyObject()
    print(m.eggs)
    
    loop._processing_action = True
    
    m._mutate_eggs([5, 6], 'insert', 0)
    m._mutate_eggs([1, 2], 'insert', 0)
    m._mutate_eggs([3, 4], 'insert', 2)
    m._mutate_eggs([7, 8], 'insert', 6)
    print(m.eggs)
    
    m._mutate_eggs([44, 55, 66], 'replace', 3)
    print(m.eggs)
    
    m._mutate_eggs(3, 'remove', 3)
    print(m.eggs)


## All prop types


@run_in_both(MyObject)
def test_property_any():  # Can be anything
    """
    True
    42
    ? Loop
    """
    m = MyObject()
    print(m.anyprop is None)  # Because None becomes null in JS
    
    m.set_anyprop(42)
    loop.iter()
    print(m.anyprop)
    
    m.set_anyprop(loop)
    loop.iter()
    print(m.anyprop)


@run_in_both(MyObject)
def test_property_bool():  # Converts to bool, no type checking
    """
    False
    True
    False
    True
    """
    m = MyObject()
    print(m.boolprop)
    
    m.set_boolprop(42)
    loop.iter()
    print(m.boolprop)
    
    m.set_boolprop('')
    loop.iter()
    print(m.boolprop)
    
    m.set_boolprop(loop)
    loop.iter()
    print(m.boolprop)


@run_in_both(MyObject)
def test_property_int():  # typechecking, but converts from float/str
    """
    0
    42
    9
    ? TypeError
    9
    """
    m = MyObject()
    print(m.intprop)
    
    m.set_intprop(42.9)
    loop.iter()
    print(m.intprop)
    
    m.set_intprop('9')  # actually, '9.1' would fail on Python
    loop.iter()
    print(m.intprop)

    m.set_intprop(loop)  # fail
    loop.iter()
    print(m.intprop)


@run_in_both(MyObject)
def test_property_float():  # typechecking, but converts from int/str
    """
    ? 0
    42.9
    9.1
    ? TypeError
    9.1
    """
    m = MyObject()
    print(m.floatprop)
    
    m.set_floatprop(42.9)
    loop.iter()
    print(m.floatprop)
    
    m.set_floatprop('9.1')  # actually, '9.1' would fail on Python
    loop.iter()
    print(m.floatprop)

    m.set_floatprop(loop)  # fail
    loop.iter()
    print(m.floatprop)


@run_in_both(MyObject)
def test_property_string():
    """
    .
    
    hello
    ? TypeError
    hello
    """
    print('.')
    
    m = MyObject()
    print(m.stringprop)
    
    m.set_stringprop('hello')
    loop.iter()
    print(m.stringprop)
    
    m.set_stringprop(3)
    loop.iter()
    print(m.stringprop)


# todo: I could also spell this as "(3, 4) || [3, 4]
@run_in_both(MyObject)
def test_property_tuple():
    """
    ()
    (3, 4)
    (5, 6)
    ? TypeError
    ? TypeError
    ? TypeError
    (5, 6)
    ------------
    []
    [3, 4]
    [5, 6]
    ? TypeError
    ? TypeError
    ? TypeError
    [5, 6]
    """
    m = MyObject()
    print(m.tupleprop)
    
    m.set_tupleprop((3, 4))
    loop.iter()
    print(m.tupleprop)
    
    m.set_tupleprop((5, 6))
    loop.iter()
    print(m.tupleprop)
    
    for value in [3, None, 'asd']:
        m.set_tupleprop(value)
        loop.iter()
    print(m.tupleprop)


@run_in_both(MyObject)
def test_property_list():
    """
    []
    [3, 4]
    [5, 6]
    ? TypeError
    ? TypeError
    ? TypeError
    [5, 6]
    """
    m = MyObject()
    print(m.listprop)
    
    m.set_listprop((3, 4))
    loop.iter()
    print(m.listprop)
    
    m.set_listprop((5, 6))
    loop.iter()
    print(m.listprop)
    
    for value in [3, None, 'asd']:
        m.set_listprop(value)
        loop.iter()
    print(m.listprop)


@run_in_both(MyObject)
def test_property_component():  # Can be a Component or None
    """
    True
    [False, True, False]
    [False, False, True]
    [True, False, False]
    ? TypeError
    ? TypeError
    ? TypeError
    [True, False, False]
    """
    m = MyObject()
    m1 = MyObject()
    m2 = MyObject()
    print(m.componentprop is None)
    
    m.set_componentprop(m1)
    loop.iter()
    print([m.componentprop is None, m.componentprop is m1, m.componentprop is m2])
    
    m.set_componentprop(m2)
    loop.iter()
    print([m.componentprop is None, m.componentprop is m1, m.componentprop is m2])
    
    m.set_componentprop(None)
    loop.iter()
    print([m.componentprop is None, m.componentprop is m1, m.componentprop is m2])
    
    for value in [3, loop, 'asd']:
        m.set_componentprop(value)
        loop.iter()
    print([m.componentprop is None, m.componentprop is m1, m.componentprop is m2])


## Python only

def test_more():
    
    with raises(TypeError):
        class MyObject2(event.Component):
            @event.Property
            def foo(self, v):
                pass
    
    with raises(TypeError):
        event.AnyProp(doc=3)
    
    m = MyObject()
    
    with raises(AttributeError):
        m.foo = 3
    
    assert 'anything' in m.__class__.anyprop.__doc__


run_tests_if_main()
