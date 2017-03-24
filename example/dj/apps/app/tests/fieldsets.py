from unittest.case import TestCase

from germanium.tools import assert_true, assert_false, assert_equal, assert_is_none

from pyston.utils import rfs


class FieldsetsTestCase(TestCase):

    def test_create_rfs_from_list(self):
        assert_equal(str(rfs(('a', 'b', 'b__c', 'b__g', ('d', ('e__f',))))), 'a,b(c,g),d(e(f))')
        assert_equal(str(rfs(('a', 'b', ('d', ('e__f',)), ('b', ('c',))))), 'a,b(c),d(e(f))')
        assert_equal(str(rfs(())), '')

    def test_rfs_append(self):
        fieldset = rfs(('a', 'b', 'b__c', 'b__g', ('d', ('e__f',))))
        fieldset.append('a')
        assert_equal(str(fieldset), 'a,b(c,g),d(e(f))')
        fieldset.append('a__h')
        assert_equal(str(fieldset), 'a(h),b(c,g),d(e(f))')
        fieldset.append('b__c__i')
        assert_equal(str(fieldset), 'a(h),b(c(i),g),d(e(f))')
        fieldset.append(('b', ('k')))
        assert_equal(str(fieldset), 'a(h),b(c(i),g,k),d(e(f))')

    def test_rfs_update(self):
        fieldset_a = rfs(('a', 'b', 'b__c', 'b__g', ('d', ('e__f',))))
        fieldset_b = rfs(('a__i', 'l'))

        fieldset_a.update(fieldset_b)
        assert_equal(str(fieldset_a), 'a(i),b(c,g),d(e(f)),l')
        assert_equal(str(fieldset_b), 'a(i),l')

    def test_rfs_update_with_list(self):
        fieldset_a = rfs(('a', 'b', 'b__c', 'b__g', ('d', ('e__f',))))
        fieldset_b = ('a__i', 'l')

        fieldset_a.update(fieldset_b)
        assert_equal(str(fieldset_a), 'a(i),b(c,g),d(e(f)),l')

    def test_rfs_flat(self):
        assert_equal(rfs(('a', 'b', 'b__c', 'b__g', ('d', ('e__f',)))).flat(), {'a', 'b', 'd'})

    def test_rfs_bool(self):
        assert_true(rfs(('a', 'b', 'b__c', 'b__g', ('d', ('e__f',)))))
        assert_false(rfs())
        assert_false(rfs(()))
        assert_false(rfs({}))

    def test_rfs_add(self):
        fieldset_a = rfs(('a', 'b', 'b__c', 'b__g', ('d', ('e__f',))))
        fieldset_b = rfs(('a__i', 'l'))

        fieldset_c = fieldset_a + fieldset_b
        assert_equal(str(fieldset_a), 'a,b(c,g),d(e(f))')
        assert_equal(str(fieldset_b), 'a(i),l')
        assert_equal(str(fieldset_c), 'a(i),b(c,g),d(e(f)),l')

    def test_rfs_add_list(self):
        fieldset_a = rfs(('a', 'b', 'b__c', 'b__g', ('d', ('e__f',))))
        fieldset_b = ('a__i', 'l')

        fieldset_c = fieldset_a + fieldset_b
        assert_equal(str(fieldset_a), 'a,b(c,g),d(e(f))')
        assert_equal(str(fieldset_c), 'a(i),b(c,g),d(e(f)),l')

    def test_rfs_get(self):
        fieldset = rfs(('a', 'b', 'b__c', 'b__g', ('d', ('e__f',))))
        assert_equal(str(fieldset.get('b')), 'b(c,g)')
        assert_is_none(fieldset.get('k'))
        assert_equal(str(fieldset.get('a')), 'a')

    def test_rfs_intersection(self):
        fieldset_a = rfs((('a', ('i', 'j')), 'b', 'b__c', 'b__g', ('d', ('e__f',))))
        fieldset_b = rfs(('a__i', 'b', 'l'))

        assert_equal(str(fieldset_a.intersection(fieldset_b)), 'a(i),b')
