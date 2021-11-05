.. _order:

Ordering
========

Ordering is very similar to filtering. It is provided via method ``_order_queryset`` that you can override to change
its default implementation. Resource class ``DjangoResource`` again uses manager to simplify custom modifications::

    class DjangoResource(BaseDjangoResource, BaseModelResource):
        order_manager = DefaultModelOrderManager()

        def _order_queryset(self, qs):
            if self.order_manager:
                return self.order_manager.order(self, qs, self.request)
            else:
                return qs

Method ``_order_queryset`` uses manager to order/sort output data. You can change the manager with ``order_manager``
property. If you set ``order_manager`` to ``None`` filtering will be disabled. Default order manager is
``DefaultModelOrderManager``.

Order manager
-------------

Order manager purposes are:

* parse input data that contains information about ordering and split this data to pairs <order identifier, order direction>
* check if concrete identifier is allowed to order
* convert identifiers to Django ordering identifiers
* finally apply ordering on Django QuerySet

Allowed identifiers are defined in ``order_fields`` or ``extra_order_fields`` that can be defined on model or resource
(or both).

DefaultModelOrderManager
^^^^^^^^^^^^^^^^^^^^^^^^

It is only one pre-implemented Pyston ordering manager. Input data is parsed from querystring named ``order`` or
HTTP header named ``X-Order``. Both have the same format. Order terms are split with a `,` char. Each term consists of
a direction char and an identifier. Missing direction char means ascending and char '-' means descending order.
Identifiers are very similar to Django identifiers where relations are joined with a string '__'. Example::

    first_name,-last_name,created_issues__created_at


Ordering field configuration
----------------------------

By default the fields that can be ordered is generated as a join of ``order_fields`` and ``extra_order_fields``. But
you can change this behaviour by overriding the method ``get_order_fields_rfs``. Values of ``order_fields`` and
``extra_order_fields`` are firstly taken from a resource and if they are not set in resource thay are obtained from
model RestMeta. If ``order_fields`` is not defined in RestMeta it is replaced with response of the method
``get_allowed_fields_rfs`` which returns all fields that a client of the resource can read.

As example we define two models ``Issue`` and ``User`` and two resources::

    class User(models.Model):

        created_at = models.DateTimeField(null=False, blank=False, auto_now_add=True)
        email = models.EmailField(null=False, blank=False, unique=True)
        contract = models.FileField(null=True, blank=True, upload_to='documents/')
        is_superuser = models.BooleanField(default=True)
        first_name = models.CharField(null=True, blank=True, max_length=100)
        last_name = models.CharField(null=True, blank=True, max_length=100)
        manual_created_date = models.DateTimeField(verbose_name=_('manual created date'), null=True, blank=True)

        class RestMeta:
            fields = ('created_at', 'email', 'contract', 'solving_issue', 'first_name', 'last_name', 'is_superuser',
                      'manual_created_date')
            detailed_fields = ('created_at', '_obj_name', 'email', 'contract', 'solving_issue', 'first_name',
                               'last_name', 'watched_issues__name', 'watched_issues__id', 'manual_created_date')
            general_fields = ('email', 'first_name', 'last_name', 'watched_issues__name', 'watched_issues__id',
                              'manual_created_date')
            direct_serialization_fields = ('created_at', 'email', 'contract', 'solving_issue', 'first_name',
                                           'last_name', 'manual_created_date')
            order_fields = ('email', 'solving_issue')
            extra_order_fields = ('created_at',)


    class Issue(models.Model):

        created_at = models.DateTimeField(null=False, blank=False, auto_now_add=True)
        name = models.CharField(max_length=100, null=False, blank=False)
        watched_by = models.ManyToManyField('app.User', blank=True, related_name='watched_issues')
        created_by = models.ForeignKey('app.User', null=False, blank=False, related_name='created_issues')
        solver = models.OneToOneField('app.User', null=True, blank=True, related_name='solving_issue')
        leader = models.OneToOneField('app.User', null=False, blank=False, related_name='leading_issue')
        description = models.TextField(null=True, blank=True)

        class RestMeta:
            extra_order_fields = ('solver__created_at',)


    class IssueResource(DjangoResource):

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


    class UserResource(DjangoResource):

        model = User
        create_obj_permission = True
        read_obj_permission = True
        update_obj_permission = True
        delete_obj_permission = True
        extra_order_fields = ()

As you can see ``order_fields`` and ``extra_order_fields`` are set inside model RestMeta for User model. From RestMeta
is allowed to filter three fields ('email', 'solving_issue', 'created_at'). But because extra_order_fields is overridden
inside UserResource client can order only with ('email', 'solving_issue').

Model Issue has only set ``extra_order_fields`` which allows to order Issues by ``User.created_at`` via related field
``solver``. Other order fields are generated from all readable fields which are obtained as a join of attributes
``fields``, ``detailed_fields`` and ``general_fields``.

Decorators
----------

Ordering provides one helper to support ordering for methods as well, decorator ``order_by``. We can use our issue
tracker as an example. Issue has a description, but for some reason we can only show the first 50 chars of the
description. We can order according this value too, for this purpose we can define method ``short_description``
and use ``order_by`` decorator::

    from pyston.utils.decorators import order_by

    class Issue(models.Model):

        description = models.TextField(verbose_name=_('description'), null=True, blank=True)

        @order_by('description')
        def short_description(self):
            return self.description[:50] if self.description is not None else None

You can now use order term 'short_description' to order data ``/api/issue/?order=short_description``.


Second decorator is called ``sorter_class``. The decorator is used for custom ordering sorters that uses queryset
annotation or extra method. The best method to explain it is example::

    from pyston.utils.decorators import sorter_class

    class WatchedIssuesCountSorter(ExtraSorter):

        def update_queryset(self, qs):
            return qs.annotate(**{self.order_string: Count('watched_issues')})

    @python_2_unicode_compatible
    class User(models.Model):

        email = models.EmailField(null=False, blank=False, unique=True)
        contract = models.FileField(null=True, blank=True, upload_to='documents/')
        is_superuser = models.BooleanField(default=True)
        first_name = models.CharField(null=True, blank=True, max_length=100)
        last_name = models.CharField(null=True, blank=True, max_length=100)
        manual_created_date = models.DateTimeField(null=True, blank=True)

        @sorter_class(WatchedIssuesCountSorter)
        def watched_issues_count(self):
            return self.watched_issues.count()

As you can see there is defined new sorter called ``WatchedIssuesCountSorter`` that allows sort users according to
count of watched issues. For this purpose is used annotate method of queryset which adds new computed database table
column that is used for sorting.
