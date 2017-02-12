from __future__ import unicode_literals

import json
import xml.dom.minidom

from germanium.tools import assert_true, assert_equal

from unittest.case import TestCase

from app.models import User

from pyston.serializer import serialize


class DirectSerializationTestCase(TestCase):

    def test_serialization(self):
        for i in range(10):
            User.objects.create(is_superuser=True, email='test{}@test.cz'.format(i))
        assert_true(isinstance(json.loads((serialize(User.objects.all()))), list))
        assert_true(isinstance(json.loads((serialize(User.objects.first()))), dict))

        assert_equal(
            set(json.loads((serialize(User.objects.first()))).keys()),
            {'id', 'created_at', '_obj_name', 'email', 'contract', 'solving_issue', 'first_name', 'last_name'}
        )
        assert_equal(
            set(json.loads((serialize(User.objects.first(), ('id',)))).keys()),
            {'id'}
        )

        xml.dom.minidom.parseString(serialize(User.objects.first(), converter_name='xml'))
