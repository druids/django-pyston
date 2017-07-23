.. _filters:

Filtering
=========

REST resource filtering is provided via the ``_filter_queryset method``. If you want to implement your own filtering
technique, you can override it. Its single argument ``qs`` contains data that you will filter (an instance of Django
QuerySet in case of a model resource).

A better way is to use pre-implemented managers defined in model ``BaseModelResource``::

    class BaseModelResource(DefaultRESTModelResource, BaseObjectResource):
        filter_manager = MultipleFilterManager()

        def _filter_queryset(self, qs):
            if self.filter_manager:
                return self.filter_manager.filter(self, qs, self.request)
            else:
                return qs

There method ``_filter_queryset`` uses manager to filter output data. You can change manager with ``filter_manager``
attribute. If you set ``filter_manager`` to None, filtering will be disabled. Default filter manager is
``MultipleFilterManager``.

Filter manager
--------------

The main purpose of a filter manager is to parse the filter specification, construct Django ``Q`` objects and use it to
filter the data in the QuerySet. Manager has only one public method filter(self, resource, qs, request). It accepts a
resource object, a QuerySet to filter and a Django request object containing the filter specification in GET arguments.


A manager must be able to:

* validate filter specification in GET arguments
* parse this input into identifiers, operators and values
* search corresponding filter classes accorring to filter identifiers.
* check if the specific filter is allowed on the resource, i.e. if it is in filter_fields_rfs

By default, ``filter_fields_rfs`` contains all fields the user is allowed to read. These fields can be rewritten in
``RESTMeta`` class or on the resource using attributes ``filter_fields`` or ``extra_filter_fields``. Attribute
``filter_fields`` defines a list of fields that are allowed to filter by and ``extra_filter_fields`` extends the list.
The rule of resource fields overriding the values from ``RESTMeta`` class of the model applies just like with other REST
fields attributes.

Pyston provides three pre-implemented managers::

DefaultFilterManager
^^^^^^^^^^^^^^^^^^^^

Manager that allows complex filter conditions with AND, OR and NOT operators. It allows use brackets too. Example of
filter string can be ``created_at__moth=5 AND NOT (contract=null OR first_name='Petr')``. Filter string can be defined
by query string names filter or by HTTP header named X-Filter.

QueryStringFilterManager
^^^^^^^^^^^^^^^^^^^^^^^^

Second manager allows only simple list of filters that is joined only with AND operator. One filter term is defined
with one query string value. Example: ``created_at__moth=5&contract=__none__``


MultipleFilterManager
^^^^^^^^^^^^^^^^^^^^^

Because pyston provides backward compatibility this manager joins ``DefaultFilterManager`` and
``QueryStringFilterManager`` to one manager. Client of REST resource can chose which filtering method will use.

Filtering field configuration
-----------------------------

Fields that can be filtered are generated as a join of ``filter_fields`` and ``extra_fields_fields``. You can
change this behaviour by overriding the method ``get_filter_fields_rfs``. The values ``filter_fields`` and
``extra_filter_fields`` are first taken from a resource and if thay are not set in the resource theayare  obtained
from the model RESTMeta. If the value ``filter_fields`` is not defined in RESTMeta, the value ``filter_fields`` is
replaces with response of method ``get_allowed_fields_rfs`` which returns all fields that a client of resource can
read. The only exception of filters that needn't be explicitly allowed are resource filters becaouse they are always
allowed.

As example we define can youse issue tracker with models ``Issue`` and ``User`` and two resources::

    class User(models.Model):

        created_at = models.DateTimeField(null=False, blank=False, auto_now_add=True)
        email = models.EmailField(null=False, blank=False, unique=True)
        contract = models.FileField(null=True, blank=True, upload_to='documents/')
        is_superuser = models.BooleanField(default=True)
        first_name = models.CharField(null=True, blank=True, max_length=100)
        last_name = models.CharField(null=True, blank=True, max_length=100)
        manual_created_date = models.DateTimeField(verbose_name=_('manual created date'), null=True, blank=True)

        class RESTMeta:
            fields = ('created_at', 'email', 'contract', 'solving_issue', 'first_name', 'last_name', 'is_superuser',
                      'manual_created_date')
            detailed_fields = ('created_at', '_obj_name', 'email', 'contract', 'solving_issue', 'first_name',
                               'last_name', 'watched_issues__name', 'watched_issues__id', 'manual_created_date')
            general_fields = ('email', 'first_name', 'last_name', 'watched_issues__name', 'watched_issues__id',
                              'manual_created_date')
            direct_serialization_fields = ('created_at', 'email', 'contract', 'solving_issue', 'first_name',
                                           'last_name', 'manual_created_date')
            filter_fields = ('email', 'first_name', 'last_name')
            extra_filter_fields = ('created_at',)


    class Issue(models.Model):

        created_at = models.DateTimeField(null=False, blank=False, auto_now_add=True)
        name = models.CharField(max_length=100, null=False, blank=False)
        watched_by = models.ManyToManyField('app.User', blank=True, related_name='watched_issues')
        created_by = models.ForeignKey('app.User', null=False, blank=False, related_name='created_issues')
        solver = models.OneToOneField('app.User', null=True, blank=True, related_name='solving_issue')
        leader = models.OneToOneField('app.User', null=False, blank=False, related_name='leading_issue')
        description = models.TextField(null=True, blank=True)

        class RESTMeta:
            extra_filter_fields = ('solver__created_at',)


    class IssueResource(BaseModelResource):

        model = Issue
        fields = ('id', 'created_at', '_obj_name', 'name', ('created_by', ('id', 'contract', 'created_at')), 'solver',
                  'leader', 'watched_by')
        detailed_fields = ('id', 'created_at', '_obj_name', 'name', ('created_by', ('id', 'contract',)), 'solver',
                           'leader', 'watched_by')
        general_fields = ('id', '_obj_name', 'name', ('created_by', ('id', 'contract', 'created_at')), 'watched_by')
        create_obj_permission = True
        read_obj_permission = True
        update_obj_permission = True
        delete_obj_permission = True


    class UserResource(BaseModelResource):

        model = User
        create_obj_permission = True
        read_obj_permission = True
        update_obj_permission = True
        delete_obj_permission = True
        extra_filter_fields = ()

Atributes ``filter_fields`` and ``extra_filter_fields`` are set inside model RESTMeta for User model. RESTMeta
configuration allows to filter four fields ('email', 'first_name', 'last_name', 'created_at'). But because
extra_filter_fields is  overridden inside UserResource client can filter only with ('email', 'first_name', 'last_name').

Model Issue only sets ``extra_filter_fields`` where it is allowed to filter Issues by ``User.created_at`` via related
field ``solver``. Other filter fields are generated from all readable fields which are obtained as a join of attributes
``fields``, ``detailed_fields`` and ``general_fields``.


Filters
-------

Filter is used for converting triple <identifier, operator, value> to a specific Q object. There are three types of
filters:

 * resource filter that is defined inside a resource and is not related to the a model field, method or resource method
 * method filter that is related to a method
 * field filter that is related to a model field

Field filter
^^^^^^^^^^^^

Field filter is always joined to specific model field. Most django fields have predefined filters:

* BooleanField - BooleanFieldFilter
* NullBooleanField - NullBooleanFieldFilter
* TextField - StringFieldFilter
* CharField - StringFieldFilter
* IntegerField - IntegerFieldFilter
* FloatField - FloatFieldFilter
* DecimalField - DecimalFieldFilter
* AutoField - IntegerFieldFilter
* DateField - DateFilter
* DateTimeField - DateTimeFilter
* GenericIPAddressField - GenericIPAddressFieldFilter
* IPAddressField - IPAddressFilterFilter
* ManyToManyField - ManyToManyFieldFilter
* ForeignKey - ForeignKeyFilter
* ForeignObjectRel - ForeignObjectRelFilter
* SlugField - CaseSensitiveStringFieldFilter
* EmailField - CaseSensitiveStringFieldFilter


BooleanFieldFilter
__________________

Boolean filter accepts operators ``eq``, ``neq, ``lt, ``gt`` (for complex filters it is operators ``=, !=, < >``).
Filter accepts only values ``1``, ``0`` (for complex filters ``True``, ``False``).

NullBooleanFieldFilter
______________________

This filter extends ``BooleanFieldFilter`` with null (query string manager ``__null__``, complex filter manager
``null``) value.

StringFieldFilter
_________________

String field accepts all string values (complex filter manager must have string values quoted with ``"`` or ``'``).
Allowed operators are ``eq``, ``neq``, ``lt``, ``gt``, ``contains``, ``icontains``, ``exact``, ``iexact``,
``startswith``, ``istartswith``, ``endswith``, ``iendswith``, ``lte``, ``gte``, ``in``.

IntegerFieldFilter
__________________

Integer filter only accepta only integer numbers and supports operators ``eq``, ``neq``, ``lt``, ``gt``, ``lte``,
``gte``, ``in``.

FloatFieldFilter
________________

Float filter accepts numbers with decimal point (``.``) and supports operators ``eq``, ``neq``, ``lt``, ``gt``, ``lte``,
``gte``, ``in``.

DecimalFieldFilter
__________________

Decimal filter accepts numbers with decimal point (``.``) and supports operators ``eq``, ``neq``, ``lt``, ``gt``,
``lte``, ``gte``, ``in``. Difference between ``FloatFieldFilter`` and ``DecimalFieldFilter`` is that
``DecimalFieldFilter`` doesn't lose accuracy.

DateFilter
__________

Date filter accepts values in ISO-8601 format. Allowed operators are ``eq``, ``neq``, ``lt``, ``gt``, ``lte``, ``gte``,
``in``, ``contains``. Date filter has two specifics. First one is operator ``contains``. With this operator you can
send value in a format other than is ISO-8601, for example send date without day (e.q. '05-2017'). The second
difference is identifier suffixes, date filter provides three suffixes ``day``, ``month``, ``year`` which you can add
to the identifier and filter date according to its day, month or year. For example if you will use filter
``created_at__day=28`` result will be all data that was created 28th day of any month.

DateTimeFilter
______________

Datetime filter is similar to DateFilter. There are only more suffixes ``day``, ``month``, ``year``, ``hour``,
``minute``, ``second``.

GenericIPAddressFieldFilter
___________________________

The filter extends ``StringFieldFilter`` with validation whether the input value is IPv4 or IPv6 address.

IPAddressFieldFilter
____________________

The filter extends ``StringFieldFilter`` with validation whether the input value is IPv4 address.

CaseSensitiveStringFieldFilter
______________________________

The filter is similar to ``StringFieldFilter`` but doesn't allow operators that is case insensitive.

ForeignKeyFilter
________________

Foreign key filter is used for filtering foreign key objects. Value is validated according to object PK format (for
example if PK should be integer that value must be integer). Allowed operators are ``eq``, ``neq``, ``lt``, ``gt``,
``lte``, ``gte``, ``in``.

ManyToManyFieldFilter
_____________________

The filter is used for filtering m2m relations. Only two operators are allowed  ``in``, ``all``. Operator ``in`` means
that one of related object from value must be inside m2m relation, ``all`` means that all values inside list must be
related through field with returned object.


ForeignObjectRelFilter
______________________

The filter is used for filtering m2o relations. Only two operators are allowed  ``in``, ``all``. Operator ``in`` means
that one of related object from value must be inside m2m relation, ``all`` means that all values inside list must be
related through field with returned object.


Custom field filter
___________________

Because Pyston improves django model fields (monkey patch) you can very simply change default field filter::

    from pyston.utils.decorators import order_by
    from pyston.filters.default_filters import StringFieldFilter, OPERATORS, CONTAINS


    class OnlyContainsStringFieldFilter(StringFieldFilter):

        operators = (
            (OPERATORS.CONTAINS, CONTAINS),
        )


    class User(models.Model):

        email = models.EmailField(verbose_name=_('email'), null=False, blank=False, unique=True,
                                  filter=OnlyContainsStringFieldFilter)

In this case we defined custom ``OnlyContainsStringFieldFilter`` that has restricted operators to only one ``contains``.

Method filter
^^^^^^^^^^^^^

Method filter is related with concrete model or resource method. To simplify filter definition Pyston provides decorator
``filter_class``. For example we can implement filter that returns users with concrete number of watched issues, for
this purpose we can use ``IntegerFieldFilterMixin`` that provides clean value method that will ensure that value will
be integer and ``SimpleMethodEqualFilter`` class::


    from pyston.utils.decorators import filter_class
    from pyston.filters.default_filters import IntegerFieldFilterMixin, SimpleMethodEqualFilter

    class WatchedIssuesCountMethodFilter(IntegerFieldFilterMixin, SimpleMethodEqualFilter):

        def get_filter_term(self, value, operator_slug, request):
            return {
                'pk__in': User.objects.annotate(
                    watched_issues_count=Count('watched_issues')
                ).filter(watched_issues_count=value).values('pk')
            }

    class User(models.Model):

        @filter_class(WatchedIssuesCountMethodFilter)
        def watched_issues_count(self):
            return self.watched_issues.count()

Now you can use filter ``/api/user?watched_issues_count=2`` and result will be all users that watch two issues.

Second way to filter method result is to use decorator ``filter_by``. Filter by decorator adds a way to filter data
by using a field filter, for example::

    from pyston.utils.decorators import filter_by

    class Issue(models.Model):

        description = models.TextField(null=True, blank=True)

        @filter_by('description')
        def short_description(self):
            return self.description[:50] if self.description is not None else None

As you can see we have created a method ``short_description`` that returns max. 50 chars long value of field descripton.
But we can filter this value the same way as a description field. For this purpose we use decorator ``filter_by``.
URL example with filter is ``/api/user?short_description=test``.

Resource filter
^^^^^^^^^^^^^^^

Resource filters are neither related to a model field nor a method. The filter must be defined in a resource with
property ``filters``. As mentioned before, these filters don't have to be allowed inside ``filter_fields`` or
``extra_filter_fields``::

    from django.db.models import F, Q

    from pyston.filters.default_filters import SimpleEqualFilter, BooleanFilterMixin


    class OvertimeIssuesFilter(BooleanFilterMixin, SimpleEqualFilter):

        def get_filter_term(self, value, operator_slug, request):
            filter_term = Q(**{
                'solving_issue__in': Issue.objects.filter(logged_minutes__gt=F('estimate_minutes')).values('pk')
            })
            return filter_term if value else ~filter_term

    class UserResource(BaseModelResource):

        model = User
        create_obj_permission = True
        read_obj_permission = True
        update_obj_permission = True
        delete_obj_permission = True
        filters = {
            'issues__overtime': OvertimeIssuesFilter
        }


We created filter that filters users according to solving issues. If filter input value is ``True`` resource returns
users which solve issues that are overtime. URL with filter is ``/api/user?issues__overtime=1``.
