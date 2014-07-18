import json

try:
    # yaml isn't standard with python.  It shouldn't be required if it
    # isn't used.
    import yaml
except ImportError:
    yaml = None

from .emitters import Emitter, XMLEmitter, JSONEmitter, PickleEmitter, CsvEmitter, YAMLEmitter
from .mimers import Mimer


Emitter.register('xml', XMLEmitter, 'text/xml; charset=utf-8')
Mimer.register(lambda *a: None, ('text/xml',))

Emitter.register('json', JSONEmitter, 'application/json; charset=utf-8')
Mimer.register(json.loads, ('application/json',))

if yaml:  # Only register yaml if it was import successfully.
    Emitter.register('yaml', YAMLEmitter, 'application/x-yaml; charset=utf-8')
    Mimer.register(lambda s: dict(yaml.safe_load(s)), ('application/x-yaml',))


Emitter.register('pickle', PickleEmitter, 'application/python-pickle')

"""
WARNING: Accepting arbitrary pickled data is a huge security concern.
The unpickler has been disabled by default now, and if you want to use
it, please be aware of what implications it will have.

Read more: http://nadiana.com/python-pickle-insecure

Uncomment the line below to enable it. You're doing so at your own risk.
"""
# Mimer.register(pickle.loads, ('application/python-pickle',))


Emitter.register('csv', CsvEmitter, 'text/csv')