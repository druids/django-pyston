from __future__ import unicode_literals

from django.db import models
from django.utils.translation import ugettext_lazy as _


class User(models.Model):

    email = models.EmailField(verbose_name=_('Email'), null=False, blank=False, unique=True)

    def __unicode__(self):
        return 'user: %s' % self.email


class Issue(models.Model):

    name = models.CharField(verbose_name=_('Name'), max_length=100, null=False, blank=False)
    watched_by = models.ManyToManyField('app.User', verbose_name=_('Watched by'), null=True, blank=True,
                                        related_name='watched_issues')
    created_by = models.ForeignKey('app.User', verbose_name=_('Created by'), null=False, blank=False,
                                   related_name='created_issues')

    def __unicode__(self):
        return 'issue: %s' % self.name
