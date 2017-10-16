"""
This example implements a simple class to hold a persons name, and three
ways to connect a function that will be print a greet when the name is
changed.
"""

from flexx import event

class Name(event.Component):
    
    first_name = event.prop('John', setter=str)
    last_name = event.prop('Doe', setter=str)
    
    # @event.prop
    # def first_name(self, n='John'):
    #     return str(n)
    
    @event.reaction('first_name', 'last_name')
    def greet1(self, *events):
        print('Hello %s %s' % (self.first_name, self.last_name))
    
    #@event.react
    def greet2(self):
        print('Hello %s %s' % (self.first_name, self.last_name))
    
    count = event.prop(0, 'The count so far')
    
    @event.action
    def add(self):
        self._set_count(self.count + 1)
    
    @event.action
    def reset(self, v=0):
        self._mutate('count', v)


name = Name()

# Connect a function using a decorator
@name.reaction('first_name', 'last_name')
def greet2(*events):
    print('Hi %s %s' % (name.first_name, name.last_name))

# Connect a function using the classic approach
def greet3(*events):
    print('Heya %s %s' % (name.first_name, name.last_name))
name.reaction(greet3, 'first_name', 'last_name')


# name.first_name = 'Jane'

event.loop.iter()
