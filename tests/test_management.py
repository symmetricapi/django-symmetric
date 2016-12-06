from django.test import TestCase

from symmetric.management.functions import *

class ApiManagementTest(TestCase):

	_VERBOSE = 'Hello World Test'
	_CAMEL_CASE = 'HelloWorldTest'

	def test_functions(self):
		self.assertEqual(verbose_to_camel_case(ApiManagementTest._VERBOSE), ApiManagementTest._CAMEL_CASE)
		self.assertEqual(verbose_to_camel_case(ApiManagementTest._VERBOSE.lower()), ApiManagementTest._CAMEL_CASE)
		self.assertEqual(verbose_to_camel_case(ApiManagementTest._VERBOSE.upper()), ApiManagementTest._CAMEL_CASE)

		self.assertEqual(camel_case_to_verbose(ApiManagementTest._CAMEL_CASE), ApiManagementTest._VERBOSE)

		self.assertTrue(TestCase in get_base_classes(ApiManagementTest))
		self.assertTrue(object in get_base_classes(ApiManagementTest))

		test_list = range(10)
		self.assertTrue(is_sublist(test_list, test_list[0:2]))
		self.assertTrue(is_sublist(test_list, test_list[-2:-1]))
		self.assertTrue(is_sublist(test_list, test_list[2:4]))
		self.assertFalse(is_sublist(test_list, [test_list[0], test_list[-1] + 10]))
