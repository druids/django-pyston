from __future__ import unicode_literals

from unittest.case import TestCase

from germanium.anotations import data_provider
from germanium.tools import assert_true, assert_false

from pyston.converters import is_serializable_collection


class ConvertersTestCase(TestCase):

    serializable_collections = (
        ([0],),
        (set([0]),),
        ((_ for _ in range(5)),),
        ((0,),),
    )

    @data_provider(serializable_collections)
    def test_should_return_true_for_serializable_collection(self, coll):
        assert_true(is_serializable_collection(coll))

    nonserializable_collections = (
        (0,),
        ("0",),
        (0.0,),
        (True,),
    )

    @data_provider(nonserializable_collections)
    def test_should_return_false_for_nonserializable_collection(self, coll):
        assert_false(is_serializable_collection(coll))
