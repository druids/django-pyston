from django.db import models
from django.db.models import Count
from django.utils.translation import ugettext_lazy as _

from pyston.utils.decorators import order_by, filter_class, filter_by, allow_tags, sorter_class
from pyston.filters.filters import IntegerFilterMixin
from pyston.filters.utils import OperatorSlug
from pyston.filters.django_filters import CONTAINS, StringFieldFilter, SimpleMethodEqualFilter
from pyston.order.django_sorters import ExtraDjangoSorter


class OnlyContainsStringFieldFilter(StringFieldFilter):

    operators = (
        (OperatorSlug.CONTAINS, CONTAINS),
    )


class WatchedIssuesCountMethodFilter(IntegerFilterMixin, SimpleMethodEqualFilter):

    def get_filter_term(self, value, operator, request):
        return {
            'pk__in': User.objects.annotate(
                watched_issues_count=Count('watched_issues')
            ).filter(watched_issues_count=value).values('pk')
        }


class WatchedIssuesCountSorter(ExtraDjangoSorter):

    def update_queryset(self, qs):
        return qs.annotate(**{self._get_order_string(): Count('watched_issues')})


class User(models.Model):

    created_at = models.DateTimeField(verbose_name=_('created at'), null=False, blank=False, auto_now_add=True)
    email = models.EmailField(verbose_name=_('email'), null=False, blank=False, unique=True,
                              filter=OnlyContainsStringFieldFilter)
    contract = models.FileField(_('file'), null=True, blank=True, upload_to='documents/')
    is_superuser = models.BooleanField(_('is superuser'), default=True)
    first_name = models.CharField(_('first name'), null=True, blank=True, max_length=100)
    last_name = models.CharField(_('last name'), null=True, blank=True, max_length=100)
    manual_created_date = models.DateTimeField(verbose_name=_('manual created date'), null=True, blank=True)

    @filter_class(WatchedIssuesCountMethodFilter)
    @sorter_class(WatchedIssuesCountSorter)
    def watched_issues_count(self):
        return self.watched_issues.count()

    def __str__(self):
        return 'user: %s' % self.email

    class RestMeta:
        fields = ('created_at', 'email', 'contract', 'solving_issue', 'first_name', 'last_name', 'is_superuser',
                  'manual_created_date', 'watched_issues_count')
        detailed_fields = ('created_at', '_obj_name', 'email', 'contract', 'solving_issue', 'first_name', 'last_name',
                           'watched_issues__name', 'watched_issues__id', 'manual_created_date')
        general_fields = ('email', 'first_name', 'last_name', 'watched_issues__name', 'watched_issues__id',
                          'manual_created_date', 'watched_issues_count')
        direct_serialization_fields = ('created_at', 'email', 'contract', 'solving_issue', 'first_name', 'last_name',
                                       'manual_created_date')
        order_fields = ('email', 'solving_issue', 'watched_issues_count')
        extra_order_fields = ('created_at',)
        filter_fields = ('email', 'first_name', 'last_name', 'is_superuser', 'created_issues', 'watched_issues_count')
        extra_filter_fields = ('created_at',)


class Issue(models.Model):

    created_at = models.DateTimeField(verbose_name=_('created at'), null=False, blank=False, auto_now_add=True)
    name = models.CharField(verbose_name=_('name'), max_length=100, null=False, blank=False)
    watched_by = models.ManyToManyField('app.User', verbose_name=_('watched by'), blank=True,
                                        related_name='watched_issues')
    created_by = models.ForeignKey('app.User', verbose_name=_('created by'), null=False, blank=False,
                                   related_name='created_issues', on_delete=models.CASCADE)
    solver = models.OneToOneField('app.User', verbose_name=_('solver'), null=True, blank=True,
                                  related_name='solving_issue', on_delete=models.CASCADE)
    leader = models.OneToOneField('app.User', verbose_name=_('leader'), null=False, blank=False,
                                  related_name='leading_issue', on_delete=models.CASCADE)
    description = models.TextField(verbose_name=_('description'), null=True, blank=True)
    logged_minutes = models.IntegerField(verbose_name=_('logged minutes'), null=True, blank=True)
    estimate_minutes = models.IntegerField(verbose_name=_('logged minutes'), null=True, blank=True)
    tags = models.TextField(verbose_name=_('tags'), null=True, blank=True)

    @filter_by('description')
    @order_by('description')
    @allow_tags
    def short_description(self):
        return self.description[:50] if self.description is not None else None

    def __str__(self):
        return 'issue: <b>%s</b>' % self.name

    class RestMeta:
        extra_order_fields = ('solver__created_at',)
        extra_filter_fields = ('solver__created_at',)