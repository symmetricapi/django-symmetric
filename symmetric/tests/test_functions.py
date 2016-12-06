from django.test import TestCase

from api.functions import *

class ApiFunctionsTest(TestCase):

	def assertAttributes(self, obj, **attrs):
		for key, value in attrs.items():
			self.assertEqual(getattr(obj, key), value)

	def test_decoding(self):
		self.assertIsNone(decode_int(None))
		self.assertIsNone(decode_int(''))
		self.assertEqual(decode_int("5"), 5)
		self.assertEqual(decode_int(5.6), 5)
		self.assertIsNone(decode_bool(None))
		self.assertIsNone(decode_bool(''))
		self.assertFalse(decode_bool("FALSE"))
		self.assertFalse(decode_bool("F"))
		self.assertFalse(decode_bool("off"))
		self.assertFalse(decode_bool(0))
		self.assertTrue(decode_bool(True))
		self.assertFalse(decode_bool(False))

	def test_datetimes(self):
		self.assertAttributes(iso_8601_to_date('2013-01-14'), year=2013, month=1, day=14)
		self.assertAttributes(iso_8601_to_date('2013-01-14T16:45:56Z'), year=2013, month=1, day=14)
		self.assertAttributes(iso_8601_to_datetime('2013-01-14T16:45:56Z'), year=2013, month=1, day=14, hour=16, minute=45, second=56)
		self.assertAttributes(iso_8601_to_datetime('2013-01-14T16:45:56.105Z'), year=2013, month=1, day=14, hour=16, minute=45, second=56)
		self.assertAttributes(iso_8601_to_datetime('2013-01-14T16:45:56+04:25'), year=2013, month=1, day=14, hour=16, minute=45, second=56)
		self.assertAttributes(iso_8601_to_datetime('2013-01-14T16:45:56.105+04:25'), year=2013, month=1, day=14, hour=16, minute=45, second=56)
