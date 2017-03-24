from django.test import TestCase

from symmetric.management.translate import translate_code

class TranslateTest(TestCase):

	def test_comparison(self):
		code = '0 != 1'
		self.assertEqual(translate_code(code, 'js'), '0 !== 1')
		self.assertEqual(translate_code(code, 'es6'), '0 !== 1')
		self.assertEqual(translate_code(code, 'java'), code)
		self.assertEqual(translate_code(code, 'objc'), code)
		self.assertEqual(translate_code(code, 'swift'), code)

	def test_none(self):
		code = 'None'
		self.assertEqual(translate_code(code, 'js'), 'void(0)')
		self.assertEqual(translate_code(code, 'es6'), 'void(0)')
		self.assertEqual(translate_code(code, 'java'), 'null')
		self.assertEqual(translate_code(code, 'objc'), 'nil')
		self.assertEqual(translate_code(code, 'swift'), 'nil')

	def test_str_format(self):
		code = '"The %s dog is %s at %dpm" % (adj, \'happy\', z + 1)'
		self.assertEqual(translate_code(code, 'js'), '"The %s dog is %s at %dpm".replace(/%[sdfg]/, adj).replace(/%[sdfg]/, "happy").replace(/%[sdfg]/, (z + 1))')
		self.assertEqual(translate_code(code, 'es6'), '`The ${adj} dog is ${"happy"} at ${(z + 1)}pm`')
		self.assertEqual(translate_code(code, 'java'), 'String.format("The %s dog is %s at %dpm", adj, "happy", (z + 1))')
		self.assertEqual(translate_code(code, 'objc'), '[NSString stringWithFormat:@"The %@ dog is %@ at %dpm", adj, @"happy", (z + 1)]')
		self.assertEqual(translate_code(code, 'swift'), 'String(format:"The %@ dog is %@ at %dpm", adj, "happy", (z + 1))')

	def test_substring(self):
		code = 'x[1:5]'
		self.assertEqual(translate_code(code, 'js'), 'x.substring(1, 5)')
		self.assertEqual(translate_code(code, 'es6'), 'x.substring(1, 5)')
		self.assertEqual(translate_code(code, 'java'), 'x.substring(1, 5)')
		self.assertEqual(translate_code(code, 'objc'), '[x substringWithRange:NSMakeRange(1, (5 - 1))]')
		self.assertEqual(translate_code(code, 'swift'), '(x as NSString).substring(with: NSMakeRange(1, (5 - 1)))')
