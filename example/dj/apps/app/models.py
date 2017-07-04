from __future__ import unicode_literals

from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.utils.encoding import python_2_unicode_compatible


@python_2_unicode_compatible
class User(models.Model):

    created_at = models.DateTimeField(verbose_name=_('created at'), null=False, blank=False, auto_now_add=True)
    email = models.EmailField(verbose_name=_('email'), null=False, blank=False, unique=True)
    contract = models.FileField(_('file'), null=True, blank=True, upload_to='documents/')
    is_superuser = models.BooleanField(_('is superuser'), default=True)
    first_name = models.CharField(_('first name'), null=True, blank=True, max_length=100)
    last_name = models.CharField(_('last name'), null=True, blank=True, max_length=100)
    manual_created_date = models.DateTimeField(verbose_name=_('manual created date'), null=True, blank=True)

    def __str__(self):
        return 'user: %s' % self.email

    class RESTMeta:
        fields = ('created_at', 'email', 'contract', 'solving_issue', 'first_name', 'last_name', 'is_superuser',
                  'manual_created_date')
        detailed_fields = ('created_at', '_obj_name', 'email', 'contract', 'solving_issue', 'first_name', 'last_name',
                           'watched_issues__name', 'watched_issues__id', 'manual_created_date')
        general_fields = ('email', 'first_name', 'last_name', 'watched_issues__name', 'watched_issues__id',
                          'manual_created_date')
        direct_serialization_fields = ('created_at', 'email', 'contract', 'solving_issue', 'first_name', 'last_name',
                                       'manual_created_date')


@python_2_unicode_compatible
class Issue(models.Model):

    created_at = models.DateTimeField(verbose_name=_('created at'), null=False, blank=False, auto_now_add=True)
    name = models.CharField(verbose_name=_('name'), max_length=100, null=False, blank=False)
    watched_by = models.ManyToManyField('app.User', verbose_name=_('watched by'), blank=True,
                                        related_name='watched_issues')
    created_by = models.ForeignKey('app.User', verbose_name=_('created by'), null=False, blank=False,
                                   related_name='created_issues')
    solver = models.OneToOneField('app.User', verbose_name=_('solver'), null=True, blank=True,
                                  related_name='solving_issue')
    leader = models.OneToOneField('app.User', verbose_name=_('leader'), null=False, blank=False,
                                  related_name='leading_issue')
    description = models.TextField(verbose_name=_('description'), null=True, blank=True)

    def __str__(self):
        return 'issue: %s' % self.name
