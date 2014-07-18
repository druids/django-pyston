import time
import csv
import cStringIO
import codecs

from django.http import HttpResponse
from django.core.cache import cache
from django import get_version as django_version
from django.utils.translation import ugettext as _
from django.template.defaultfilters import lower
from django.db.models.fields.related import RelatedField
from django.utils.encoding import force_text

from .decorator import decorator
from .version import get_version


def format_error(error):
    return u"Piston/%s (Django %s) crash report:\n\n%s" % \
        (get_version(), django_version(), error)


class rc_factory(object):
    """
    Status codes.
    """
    CODES = dict(ALL_OK=({'success': _('OK')}, 200),
                 CREATED=({'success': _('The record was created')}, 201),
                 DELETED=('', 204),  # 204 says "Don't send a body!"
                 BAD_REQUEST=({'error': _('Bad Request')}, 400),
                 FORBIDDEN=({'error':_('Forbidden')}, 401),
                 NOT_FOUND=({'error':_('Not Found')}, 404),
                 DUPLICATE_ENTRY=({'error': _('Conflict/Duplicate')}, 409),
                 NOT_HERE=({'error': _('Gone')}, 410),
                 UNSUPPORTED_MEDIA_TYPE=({'error': _('Unsupported Media Type')}, 415),
                 INTERNAL_ERROR=({'error': _('Internal server error')}, 500),
                 NOT_IMPLEMENTED=({'error': _('Not implemented')}, 501),
                 THROTTLED=({'error': _('The resource was throttled')}, 503))

    def __getattr__(self, attr):
        """
        Returns a fresh `HttpResponse` when getting
        an "attribute". This is backwards compatible
        with 0.2, which is important.
        """
        try:
            (r, c) = self.CODES.get(attr)
        except TypeError:
            raise AttributeError(attr)

        class HttpResponseWrapper(HttpResponse):
            """
            Wrap HttpResponse and make sure that the internal_base_content_is_iter 
            flag is updated when the _set_content method (via the content
            property) is called
            """
            def _set_content(self, content):
                """
                type of the value parameter. This logic is in the construtor
                for HttpResponse, but doesn't get repeated when setting
                HttpResponse.content although this bug report (feature request)
                suggests that it should: http://code.djangoproject.com/ticket/9403
                """
                if not isinstance(content, basestring) and hasattr(content, '__iter__'):
                    self._container = {'messages': content}
                    self._base_content_is_iter = True
                else:
                    self._container = [content]
                    self._base_content_is_iter = False

            content = property(HttpResponse.content.getter, _set_content)

        return HttpResponseWrapper(r, content_type='text/plain', status=c)

rc = rc_factory()


class FormValidationError(Exception):
    def __init__(self, form):
        self.form = form


class HttpStatusCode(Exception):
    def __init__(self, response):
        self.response = response


def validate(v_form, operation='POST'):
    @decorator
    def wrap(f, self, request, *a, **kwa):
        form = v_form(getattr(request, operation), request.FILES)

        if form.is_valid():
            setattr(request, 'form', form)
            return f(self, request, *a, **kwa)
        else:
            raise FormValidationError(form)
    return wrap


def throttle(max_requests, timeout=60 * 60, extra=''):
    """
    Simple throttling decorator, caches
    the amount of requests made in cache.
    
    If used on a view where users are required to
    log in, the username is used, otherwise the
    IP address of the originating request is used.
    
    Parameters::
     - `max_requests`: The maximum number of requests
     - `timeout`: The timeout for the cache entry (default: 1 hour)
    """
    @decorator
    def wrap(f, self, request, *args, **kwargs):
        if request.user.is_authenticated():
            ident = request.user.username
        else:
            ident = request.META.get('REMOTE_ADDR', None)

        if hasattr(request, 'throttle_extra'):
            """
            Since we want to be able to throttle on a per-
            application basis, it's important that we realize
            that `throttle_extra` might be set on the request
            object. If so, append the identifier name with it.
            """
            ident += ':%s' % str(request.throttle_extra)

        if ident:
            """
            Preferrably we'd use incr/decr here, since they're
            atomic in memcached, but it's in django-trunk so we
            can't use it yet. If someone sees this after it's in
            stable, you can change it here.
            """
            ident += ':%s' % extra

            now = time.time()
            count, expiration = cache.get(ident, (1, None))

            if expiration is None:
                expiration = now + timeout

            if count >= max_requests and expiration > now:
                t = rc.THROTTLED
                wait = int(expiration - now)
                t.content = 'Throttled, wait %d seconds.' % wait
                t['Retry-After'] = wait
                return t

            cache.set(ident, (count + 1, expiration), (expiration - now))

        return f(self, request, *args, **kwargs)
    return wrap


def coerce_put_post(request):
    """
    Django doesn't particularly understand REST.
    In case we send data over PUT, Django won't
    actually look at the data and load it. We need
    to twist its arm here.
    
    The try/except abominiation here is due to a bug
    in mod_python. This should fix it.
    """
    if request.method == "PUT":
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

        try:
            request.method = "POST"
            request._load_post_and_files()
            request.method = "PUT"
        except AttributeError:
            request.META['REQUEST_METHOD'] = 'POST'
            request._load_post_and_files()
            request.META['REQUEST_METHOD'] = 'PUT'

        request.PUT = request.POST


def model_resources_to_dict():
    from resource import resource_tracker

    model_resources = {}
    for resource in resource_tracker:
        if hasattr(resource, 'model'):
            model = resource.model
            model_label = lower('%s.%s' % (model._meta.app_label, model._meta.object_name))
            model_resources[model_label] = resource
    return model_resources


def model_default_rest_fields(model):
    rest_fields = []
    for field in model._meta.fields:
        if isinstance(field, RelatedField):
            rest_fields.append((field.name, ('id', '_obj_name', '_rest_links')))
        else:
            rest_fields.append(field.name)
    return rest_fields


def get_resource_of_model(model):
    model_label = lower('%s.%s' % (model._meta.app_label, model._meta.object_name))
    return model_resources_to_dict().get(model_label)


def list_to_dict(list_obj):
    dict_obj = {}
    for val in list_obj:
        if isinstance(val, (list, tuple)):
            dict_obj[val[0]] = list_to_dict(val[1])
        else:
            dict_obj[val] = {}
    return dict_obj


def dict_to_list(dict_obj):
    list_obj = []
    for key, val in dict_obj.items():
        if val:
            list_obj.append((key, dict_to_list(val)))
        else:
            list_obj.append(key)
    return tuple(list_obj)


def join_dicts(dict_obj1, dict_obj2):
    joined_dict = dict_obj1.copy()

    for key2, val2 in dict_obj2.items():
        val1 = joined_dict.get(key2)
        if not val1:
            joined_dict[key2] = val2
        elif not val2:
            continue
        else:
            joined_dict[key2] = join_dicts(val1, val2)
    return joined_dict


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


class Enum(set):
    def __getattr__(self, name):
        if name in self:
            return name
        raise AttributeError


class HeadersResult(object):

    def __init__(self, result, http_headers={}, status_code=200):
        self.result = result
        self.http_headers = http_headers
        self.status_code = status_code


class CsvGenerator(object):

    def __init__(self, delimiter=';', quotechar='"', encoding='utf-8'):
        self.encoding = encoding
        self.quotechar = quotechar
        self.delimiter = delimiter

    def generate(self, header, data, output_stream):
        writer = UnicodeWriter(output_stream, delimiter=self.delimiter, quotechar=self.quotechar, quoting=csv.QUOTE_ALL)

        if header:
            writer.writerow(self._prepare_list(header))

        for row in data:
            writer.writerow(self._prepare_list(row))

    def _prepare_list(self, values):
        prepared_row = []

        for value in values:
            value = self._prepare_value(value.get('value') if isinstance(value, dict) else value);
            prepared_row.append(value)
        return prepared_row

    def _prepare_value(self, value):
        value = force_text(value)
        return value


class UnicodeWriter:
    """
    A CSV writer which will write rows to CSV file "f",
    which is encoded in the given encoding.
    https://docs.python.org/2/library/csv.html
    """

    def __init__(self, f, dialect=csv.excel, encoding='utf-8', **kwds):
        # Redirect output to a queue
        self.queue = cStringIO.StringIO()
        self.writer = csv.writer(self.queue, dialect=dialect, **kwds)
        self.stream = f
        self.stream.write(u'\ufeff')  # BOM for Excel
        self.encoder = codecs.getincrementalencoder(encoding)()

    def writerow(self, row):
        self.writer.writerow([s.encode('utf-8') for s in row])
        # Fetch UTF-8 output from the queue ...
        data = self.queue.getvalue()
        data = data.decode('utf-8')
        # ... and reencode it into the target encoding
        # write to the target stream
        self.stream.write(data)
        # empty queue
        self.queue.truncate(0)

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)
