import StringIO

from django.utils.html import escape

def __dump_value(t, value, tag, file):
	if t == str or t == unicode:
		file.write('<%s>%s</%s>' % (tag, escape(value), tag))
	elif t == bool:
		file.write('<%s>%s</%s>' % (tag, str(value).lower(), tag))
	else:
		file.write('<%s>%s</%s>' % (tag, str(value), tag))

def __dump_dict(dictionary, file):
	"""Output a dict."""
	for key, value in dictionary.items():
		t = type(value)
		if t == dict:
			file.write('<div class="%s">' % key)
			__dump_dict(value, file)
			file.write('</div>')
		elif t == tuple or t == list or t == set:
			file.write('<ul class="%s">' % key)
			__dump_array(value, file)
			file.write('</ul>' % key)
		else:
			__dump_value(t, value, key, file)

def __dump_array(array, file):
	"""Output an array."""
	for value in array:
		t = type(value)
		if t == dict:
			__dump_dict(value, file)
		elif t == tuple or t == list or t == set:
			file.write('<ul>')
			__dump_array(value, file)
			file.write('</ul>')
		else:
			__dump_value(t, value, 'li', file)

def dumps(data, file=None):
	"""Similar to json.dumps, will return an html fragment string."""
	if file:
		output = file
	else:
		output = StringIO.StringIO()
	__dump_array([data], output)
	if not file:
		return output.getvalue()
