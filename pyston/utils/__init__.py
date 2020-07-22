import re

from collections import OrderedDict

from django.http import HttpResponse
from django.utils.translation import ugettext_lazy as _
from django.template.defaultfilters import lower
from django.db import models
from django.utils.encoding import force_text

from copy import deepcopy

from chamber.utils.decorators import classproperty

from pyston.utils.compatibility import get_model_from_relation_or_none


LOOKUP_SEP = '__'


def coerce_rest_request_method(request):
    """
    Django doesn't particularly understand REST.
    In case we send data over PUT, Django won't
    actually look at the data and load it. We need
    to twist its arm here.

    The try/except abominiation here is due to a bug
    in mod_python. This should fix it.
    """
    if request.method in {'PUT', 'PATCH'}:
        # Bug fix: if _load_post_and_files has already been called, for
        # example by middleware accessing request.POST, the below code to
        # pretend the request is a POST instead of a PUT will be too late
        # to make a difference. Also calling _load_post_and_files will result
        # in the following exception:
        #   AttributeError: You cannot set the upload handlers after the upload has been processed.
        # The fix is to check for the presence of the _post field which is set
        # the first time _load_post_and_files is called (both by wsgi.py and
        # modpython.py). If it's set, the request has to be 'reset' to redo
        # the query value parsing in POST mode.
        if hasattr(request, '_post'):
            del request._post
            del request._files

        tmp_request_method = request.method
        try:
            request.method = 'POST'
            request._load_post_and_files()
            request.method = tmp_request_method
        except AttributeError:
            request.META['REQUEST_METHOD'] = 'POST'
            request._load_post_and_files()
            request.META['REQUEST_METHOD'] = tmp_request_method

        setattr(request, tmp_request_method, request.POST)


def model_all_available_fields(model):
    return {field.name for field in model._meta.fields}


def flat_list(list_obj):
    flat_list_obj = []
    for val in list_obj:
        if isinstance(val, (list, tuple)):
            flat_list_obj.append(val[0])
        else:
            flat_list_obj.append(val)
    return flat_list_obj


class JsonObj(dict):

    def __setattr__(self, name, value):
        self[name] = value


def model_resources_to_dict():
    from pyston.resource import resource_tracker

    model_resources = {}
    for resource in resource_tracker:
        if hasattr(resource, 'model') and issubclass(resource.model, models.Model):
            model = resource.model
            model_label = lower('{}.{}'.format(model._meta.app_label, model._meta.object_name))
            model_resources[model_label] = resource
    return model_resources


def set_rest_context_to_request(request, mapping):
    context = {}
    for key, (header_key, queryset_key) in mapping.items():
        val = request.GET.get(queryset_key, request.META.get(header_key))
        if val:
            context[key] = val
    request._rest_context = context


def is_match(regex, text):
    pattern = re.compile(regex)
    return pattern.search(text) is not None


def split_fields(fields_string):

    brackets = 0

    field = ''
    for char in fields_string:
        if char == ',' and not brackets:
            field = field.strip()
            if field:
                yield field
            field = ''
            continue

        if char == '(':
            brackets += 1

        if char == ')':
            brackets -= 1

        field += char

    field = field.strip()
    if field:
        yield field


class RESTField:

    def __init__(self, name, subfieldset=None):
        assert isinstance(name, str)
        assert subfieldset is None or isinstance(subfieldset, RESTFieldset)

        self.name = name
        self.subfieldset = subfieldset or RESTFieldset()

    def __deepcopy__(self, memo):
        return self.__class__(self.name, deepcopy(self.subfieldset))

    def join(self, rest_field):
        self.subfieldset = self.subfieldset.join(rest_field.subfieldset)
        return self

    def intersection(self, rest_field):
        self.subfieldset = self.subfieldset.intersection(rest_field.subfieldset)
        return self

    def __str__(self):
        if self.subfieldset:
            return '{}({})'.format(self.name, self.subfieldset)
        return force_text(self.name)


class RESTFieldset:

    @classmethod
    def create_from_string(cls, fields_string):
        fields = []
        for field in split_fields(fields_string):
            if is_match('^[^\(\)]+\(.+\)$', field):
                field_name, subfields_string = field[:len(field) - 1].split('(', 1)
                if LOOKUP_SEP in field_name:
                    field_name, subfields_string = field.split(LOOKUP_SEP, 1)

                subfieldset = RFS.create_from_string(subfields_string)
            else:
                field_name = field
                subfieldset = None
                if LOOKUP_SEP in field_name:
                    field_name, subfields_string = field.split(LOOKUP_SEP, 1)
                    subfieldset = RFS.create_from_string(subfields_string)

            fields.append(RESTField(field_name, subfieldset))
        return RESTFieldset(*fields)

    @classmethod
    def _create_field_from_list(cls, field):
        field_name, subfield_list = field

        return RESTField(field_name, cls.create_from_list(subfield_list))

    @classmethod
    def _create_field_from_string(cls, field):
        if LOOKUP_SEP in field:
            field_name, field_child = field.split(LOOKUP_SEP, 1)
            return RESTField(field_name, cls.create_from_list((field_child,)))
        else:
            return RESTField(field)

    @classmethod
    def create_from_list(cls, fields_list=None):
        if isinstance(fields_list, RESTFieldset):
            return deepcopy(fields_list)

        fields = []
        for field in fields_list or ():
            if isinstance(field, (list, tuple)):
                fields.append(cls._create_field_from_list(field))
            elif isinstance(field, str):
                fields.append(cls._create_field_from_string(field))
            else:
                raise ValueError('field can be only list, tuple or string ({} [{}])'.format(field, type(field)))

        return RESTFieldset(*fields)

    def __init__(self, *fields):
        self.fields_map = OrderedDict()
        for field in fields:
            if not isinstance(field, RESTField):
                field = RESTField(field)
            self.append(field)

    @property
    def fields(self):
        return self.fields_map.values()

    def join(self, rest_fieldset):
        if isinstance(rest_fieldset, (list, tuple, set)):
            rest_fieldset = self.create_from_list(rest_fieldset)

        assert isinstance(rest_fieldset, RESTFieldset)

        for rf in rest_fieldset.fields:
            if rf.name not in self.fields_map:
                self.fields_map[rf.name] = deepcopy(rf)
            else:
                self.fields_map[rf.name] = self.fields_map[rf.name].join(rf)

        return self

    def intersection(self, rest_fieldset):
        assert isinstance(rest_fieldset, RESTFieldset)

        fields_map = self.fields_map
        self.fields_map = OrderedDict()

        for name, rf in fields_map.items():
            if name in rest_fieldset.fields_map:
                self.append(rf.intersection(rest_fieldset.fields_map[name]))

        return self

    def subtract(self, rest_fieldset):
        if isinstance(rest_fieldset, (list, tuple, set)):
            rest_fieldset = RFS(*rest_fieldset)

        assert isinstance(rest_fieldset, RESTFieldset)

        fields_map = self.fields_map
        self.fields_map = OrderedDict()

        for name, rf in fields_map.items():
            if name not in rest_fieldset.fields_map:
                self.fields_map[name] = rf

        return self

    def __deepcopy__(self, memo):
        return self.__class__(*map(deepcopy, self.fields))

    def __str__(self):
        return ','.join(map(force_text, self.fields))

    def __add__(self, rest_fieldset):
        a_rfs = deepcopy(self)
        return a_rfs.join(rest_fieldset)

    def __bool__(self):
        return bool(self.fields_map)
    __nonzero__ = __bool__

    def get(self, key):
        return self.fields_map.get(key)

    def append(self, field):
        if isinstance(field, RESTField):
            rest_field = field
        elif isinstance(field, str):
            rest_field = self._create_field_from_string(field)
        elif isinstance(field, (list, tuple)):
            rest_field = self._create_field_from_list(field)
        else:
            raise ValueError('field can be only list, tuple or string ({} [{}])'.format(field, type(field)))

        if rest_field.name in self.fields_map:
            rest_field = self.fields_map[rest_field.name].join(rest_field)

        self.fields_map[rest_field.name] = rest_field
        return self

    def update(self, rest_fieldset):
        if isinstance(rest_fieldset, (list, tuple, set)):
            rest_fieldset = self.create_from_list(rest_fieldset)

        assert isinstance(rest_fieldset, RESTFieldset)

        for rf in rest_fieldset.fields:
            rf = deepcopy(rf)
            if rf.name not in self.fields_map:
                self.fields_map[rf.name] = rf
            else:
                self.fields_map[rf.name] = self.fields_map[rf.name].join(rf)

        return self

    def flat(self):
        return set(self.fields_map.keys())

    def __contains__(self, key):
        return key in self.fields_map

    def __getitem__(self, key):
        return self.get(key)


RF = RESTField
RFS = RESTFieldset
rfs = RFS.create_from_list
