import json
import xml.dom.minidom

from decimal import Decimal
from uuid import uuid4
from datetime import date, datetime, time, timedelta

from collections import OrderedDict

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
            {'id', 'created_at', 'email', 'contract', 'solving_issue', 'first_name', 'last_name', 'manual_created_date'}
        )
        assert_equal(
            set(json.loads((serialize(User.objects.first(), ('id',)))).keys()),
            {'id'}
        )

        xml.dom.minidom.parseString(serialize(User.objects.first(), converter_name='xml'))

    def test_direct_serialization_to_csv_should_create_columns_according_to_required_fieldset(self):
        data = OrderedDict((('a', 1), ('b', 2)))
        assert_equal(
            serialize(data, converter_name='csv'),
            '\ufeff\r\n'
        )
        assert_equal(
            serialize(data, converter_name='csv', requested_fieldset=('a',)),
            '\ufeff"A"\r\n"1"\r\n'
        )
        assert_equal(
            serialize(data, converter_name='csv', requested_fieldset=('a', 'b')),
            '\ufeff"A";"B"\r\n"1";"2"\r\n'
        )
        assert_equal(
            serialize(data, converter_name='csv', requested_fieldset=('a', 'b', 'c')),
            '\ufeff"A";"B";"C"\r\n"1";"2";""\r\n'
        )

    def test_direct_serialization_to_python_format_should_return_only_base_python_data(self):
        now_value = datetime.now().replace(microsecond=0)
        today_value = date.today()
        timedelta_value = timedelta(days=5, hours=2, seconds=5)
        localtime_value = now_value.time()
        uuid_value = uuid4()
        decimal_value = Decimal('105.689')

        data = OrderedDict(
            now=now_value,
            today=today_value,
            timedelta=timedelta_value,
            localtime=localtime_value,
            uuid=uuid_value,
            decimal=decimal_value,
            set={1, 2, 3}
        )

        assert_equal(
            serialize(data, converter_name='python'),
            {
                'now': now_value.isoformat(),
                'today': today_value.isoformat(),
                'timedelta': '5 days, 2:00:05',
                'localtime': localtime_value.isoformat(),
                'uuid': str(uuid_value),
                'decimal': str(decimal_value),
                'set': [1, 2, 3]
            }
        )