import os
from optparse import make_option

from django.core.management.base import BaseCommand
from django.template import Template

from api.management.generateconnections import GenerateConnectionsCommand

WITH_PARAM = '{% if param %}With{{ param }}:({{ param_type }}){{ name_lower }}{{ param }}{% endif %}'
WITH_PARENT_PARAM = '{% if param %}With{{ param }}:({{ param_type }}){{ parent_name_lower }}{{ param }}{% endif %}'
WITH_PARENT_PARAM_PARAMS = '{% if param %}With{{ param }}:({{ param_type }}){{ parent_name_lower }}{{ param }} params:(APIRequestParams *)params{% else %}WithParams:(APIRequestParams *)params{% endif %}'
FOR_PARENT = '{% if not param %}For{{ parent_name }}{% endif %}'
FOR_PARENT_PARAM = '{% if param %} for{{ parent_name }}With{{ param }}:({{ param_type }}){{ parent_name_lower }}{{ param }}{% endif %}'
WITH_PARAM_COMPLETION = '{% if param %}With{{ param }}:({{ param_type }}){{ name_lower }}{{ param }} completionHandler:(APIReadHandler)completion{% else %}WithCompletionHandler:(APIReadHandler)completion{% endif %}'
WITH_PARENT_PARAM_COMPLETION = '{% if param %}With{{ param }}:({{ param_type }}){{ parent_name_lower }}{{ param }} completionHandler:(APIReadHandler)completion{% else %}WithCompletionHandler:(APIReadHandler)completion{% endif %}'

READ_OBJECT_METHOD = """
- (void)read{{ name }}/1
{
	NSString *path = {% if param %}[NSString stringWithFormat:URL_{{ app_name|upper }}_{{ name|upper }}_WITH_{{ param|upper }}, {{ name_lower }}{{ param }}]{% else %}URL_{{ app_name|upper }}_{{ name|upper }}{% endif %};
	[self performRequestWithObject:nil action:API_ACTION_READ requestType:REQUEST_{{ app_name|upper }}_READ_{{ name|upper }} path:path https:{% if https %}YES{% else %}NO{% endif %} login:{% if login %}YES{% else %}NO{% endif %} sign:NO];
}

- (void)read{{ name }}/2
{
	self.readHandler = completion;
	[self read{{ name }}{% if param %}With{{ param }}:{{ name_lower }}{{ param }}{% endif %}];
}""".replace('/1', WITH_PARAM).replace('/2', WITH_PARAM_COMPLETION)

READ_LIST_METHOD = """
- (void)read{{ name_plural }}
{
	[self performRequestWithObject:nil action:API_ACTION_LIST requestType:REQUEST_{{ app_name|upper }}_READ_{{ name_plural|upper }} path:URL_{{ app_name|upper }}_{{ name_plural|upper }} https:{% if https %}YES{% else %}NO{% endif %} login:{% if login %}YES{% else %}NO{% endif %} sign:NO];
}

- (void)read{{ name_plural }}WithParams:(APIRequestParams *)params
{
	self.requestParams = params;
	[self read{{ name_plural }}];
}

- (void)read{{ name_plural }}WithParams:(APIRequestParams *)params completionHandler:(APIListHandler)completion
{
	self.requestParams = params;
	self.listHandler = completion;
	[self read{{ name_plural }}];
}"""

CREATE_METHOD = """
- (void)create{{ name }}:({{ name }} *){{ name_lower }}
{
	[self performRequestWithObject:{{ name_lower }} action:API_ACTION_CREATE requestType:REQUEST_{{ app_name|upper }}_CREATE_{{ name|upper }} path:URL_{{ app_name|upper }}_{{ name_plural|upper }} https:{% if https %}YES{% else %}NO{% endif %} login:{% if login %}YES{% else %}NO{% endif %} sign:{% if hmac %}YES{% else %}NO{% endif %}];
}

- (void)create{{ name }}:({{ name }} *){{ name_lower }} completionHandler:(APIHandler)completion
{
	self.completionHandler = completion;
	[self create{{ name }}:{{ name_lower }}];
}"""

UPDATE_METHOD = """
- (void)update{{ name }}:({{ name }} *){{ name_lower }}
{
	NSString *path = {% if param %}[NSString stringWithFormat:URL_{{ app_name|upper }}_{{ name|upper }}, [{{ name_lower }} objectId]]{% else %}URL_{{ app_name|upper }}_{{ name|upper }}{% endif %};
	[self performRequestWithObject:{{ name_lower }} action:API_ACTION_UPDATE requestType:REQUEST_{{ app_name|upper }}_UPDATE_{{ name|upper }} path:path https:{% if https %}YES{% else %}NO{% endif %} login:{% if login %}YES{% else %}NO{% endif %} sign:{% if hmac %}YES{% else %}NO{% endif %}];
}

- (void)update{{ name }}:({{ name }} *){{ name_lower }} completionHandler:(APIHandler)completion
{
	self.completionHandler = completion;
	[self update{{ name }}:{{ name_lower }}];
}"""

DELETE_METHOD = """
- (void)delete{{ name }}:({{ name }} *){{ name_lower }}
{
	[self performRequestWithObject:nil action:API_ACTION_DELETE requestType:REQUEST_{{ app_name|upper }}_DELETE_{{ name|upper }} path:[NSString stringWithFormat:URL_{{ app_name|upper }}_{{ name|upper }}, [{{ name_lower }} objectId]] https:{% if https %}YES{% else %}NO{% endif %} login:{% if login %}YES{% else %}NO{% endif %} sign:NO];
}

- (void)delete{{ name }}:({{ name }} *){{ name_lower }} completionHandler:(APIHandler)completion
{
	self.completionHandler = completion;
	[self delete{{ name }}:{{ name_lower }}];
}"""

READ_RELATED_LIST_METHOD = """
- (void)read{{ name_plural }}For{{ parent_name }}/1
{
	NSString *path = {% if param %}[NSString stringWithFormat:URL_{{ app_name|upper }}_{{ parent_name|upper }}_{{ name_plural|upper }}_WITH_{{ param|upper }}, {{ parent_name_lower }}{{ param }}]{% else %}URL_{{ app_name|upper }}_{{ parent_name|upper }}_{{ name_plural|upper }}{% endif %};
	[self performRequestWithObject:nil action:API_ACTION_LIST requestType:REQUEST_{{ app_name|upper }}_READ_{{ parent_name|upper }}_{{ name_plural|upper }} path:path https:{% if https %}YES{% else %}NO{% endif %} login:{% if login %}YES{% else %}NO{% endif %} sign:NO];
}

- (void)read{{ name_plural }}For{{ parent_name }}/2
{
	self.requestParams = params;
	[self read{{ name_plural }}For{{ parent_name }}{% if param %}With{{ param }}:{{ parent_name_lower }}{{ param }}{% endif %}];
}

- (void)read{{ name_plural }}For{{ parent_name }}/2 completionHandler:(APIListHandler)completion
{
	self.requestParams = params;
	self.listHandler = completion;
	[self read{{ name_plural }}For{{ parent_name }}{% if param %}With{{ param }}:{{ parent_name_lower }}{{ param }}{% endif %}];
}""".replace('/1', WITH_PARENT_PARAM).replace('/2', WITH_PARENT_PARAM_PARAMS)

CREATE_RELATED_METHOD = """
- (void)create{{ name }}/1:({{ name }} *){{ name_lower }}/2
{
	NSString *path = {% if param %}[NSString stringWithFormat:URL_{{ app_name|upper }}_{{ parent_name|upper }}_{{ name_plural|upper }}_WITH_{{ param|upper }}, {{ parent_name_lower }}{{ param }}]{% else %}URL_{{ app_name|upper }}_{{ parent_name|upper }}_{{ name_plural|upper }}{% endif %};
	[self performRequestWithObject:{{ name_lower }} action:API_ACTION_CREATE requestType:REQUEST_{{ app_name|upper }}_CREATE_{{ parent_name|upper }}_{{ name|upper }} path:path https:{% if https %}YES{% else %}NO{% endif %} login:{% if login %}YES{% else %}NO{% endif %} sign:{% if hmac %}YES{% else %}NO{% endif %}];
}

- (void)create{{ name }}/1:({{ name }} *){{ name_lower }}/2 completionHandler:(APIHandler)completion
{
	self.completionHandler = completion;
	{% if param %}[self create{{ name }}:{{ name_lower }} for{{ parent_name }}With{{ param }}:{{ parent_name_lower }}{{ param }}]{% else %}[self create{{ name }}For{{ parent_name }}:{{ name_lower }}]{% endif %};
}""".replace('/1', FOR_PARENT).replace('/2', FOR_PARENT_PARAM)

READ_RELATED_OBJECT_METHOD = """
- (void)read{{ name }}For{{ parent_name }}/1
{
	NSString *path = {% if param %}[NSString stringWithFormat:URL_{{ app_name|upper }}_{{ parent_name|upper }}_{{ name|upper }}_WITH_{{ param|upper }}, {{ parent_name_lower }}{{ param }}]{% else %}URL_{{ app_name|upper }}_{{ parent_name|upper }}_{{ name|upper }}{% endif %};
	[self performRequestWithObject:nil action:API_ACTION_READ requestType:REQUEST_{{ app_name|upper }}_READ_{{ parent_name|upper }}_{{ name|upper }} path:path https:{% if https %}YES{% else %}NO{% endif %} login:{% if login %}YES{% else %}NO{% endif %} sign:NO];
}

- (void)read{{ name }}For{{ parent_name }}/2
{
	self.readHandler = completion;
	[self read{{ name }}For{{ parent_name }}{% if param %}With{{ param }}:{{ parent_name_lower }}{{ param }}{% endif %}];
}""".replace('/1', WITH_PARENT_PARAM).replace('/2', WITH_PARENT_PARAM_COMPLETION)

UPDATE_RELATED_METHOD = """
- (void)update{{ name }}/1:({{ name }} *){{ name_lower }}/2
{
	NSString *path = {% if param %}[NSString stringWithFormat:URL_{{ app_name|upper }}_{{ parent_name|upper }}_{{ name|upper }}_WITH_{{ param|upper }}, {{ parent_name_lower }}{{ param }}]{% else %}URL_{{ app_name|upper }}_{{ parent_name|upper }}_{{ name|upper }}{% endif %};
	[self performRequestWithObject:{{ name_lower }} action:API_ACTION_UPDATE requestType:REQUEST_{{ app_name|upper }}_UPDATE_{{ parent_name|upper }}_{{ name|upper }} path:path https:{% if https %}YES{% else %}NO{% endif %} login:{% if login %}YES{% else %}NO{% endif %} sign:{% if hmac %}YES{% else %}NO{% endif %}];
}

- (void)update{{ name }}/1:({{ name }} *){{ name_lower }}/2 completionHandler:(APIHandler)completion
{
	self.completionHandler = completion;
	[self update{{ name }}{% if param %} for{{ parent_name }}With{{ param }}:{{ parent_name_lower }}{{ param }}{% else %}For{{ parent_name }}:{{ name_lower }}{% endif %}];
}""".replace('/1', FOR_PARENT).replace('/2', FOR_PARENT_PARAM)

READ_OBJECT_RESPONSE = """
			case REQUEST_{{ app_name|upper }}_READ_{{ name|upper }}:
				responseObject = [self processResponseWithClass:[{{ name }} class]];
				self.responseData = nil;
				[self completeWithSelector:@selector({{ app_name_lower }}Connection:didRead{{ name }}:) object:responseObject];
				[responseObject release];
				break;"""

READ_LIST_RESPONSE = """
			case REQUEST_{{ app_name|upper }}_READ_{{ name_plural|upper }}:
				{% if subclasses %}responseArray = [self processResponseWithClasses:@{ {% for subclass in subclasses %}@"{{ subclass.0 }}" : [@"{{ subclass.1 }}" class]{% endfor %} }];{% else %}responseArray = [self processResponseWithClass:[{{ name }} class]];{% endif %}
				self.responseData = nil;
				[self completeWithSelector:@selector({{ app_name_lower }}Connection:didRead{{ name_plural }}:) object:responseArray];
				[responseArray release];
				break;"""

CREATE_RESPONSE = """
			case REQUEST_{{ app_name|upper }}_CREATE_{{ name|upper }}:
				[tempRequestObject setObjectId:_newObjectId];
				self.responseData = nil;
				[self completeWithSelector:@selector({{ app_name_lower }}Connection:didCreate{{ name }}:) object:tempRequestObject];
				break;"""

UPDATE_RESPONSE = """
			case REQUEST_{{ app_name|upper }}_UPDATE_{{ name|upper }}:
				self.responseData = nil;
				[self completeWithSelector:@selector({{ app_name_lower }}Connection:didUpdate{{ name }}:) object:tempRequestObject];
				break;"""

DELETE_RESPONSE = """
			case REQUEST_{{ app_name|upper }}_DELETE_{{ name|upper }}:
				self.responseData = nil;
				[self completeWithSelector:@selector({{ app_name_lower }}Connection:didDelete{{ name }}:) object:tempRequestObject];
				break;"""

READ_RELATED_LIST_RESPONSE = """
			case REQUEST_{{ app_name|upper }}_READ_{{ parent_name|upper }}_{{ name_plural|upper }}:
				{% if subclasses %}responseArray = [self processResponseWithClasses:@{ {% for subclass in subclasses %}@"{{ subclass.0 }}" : [@"{{ subclass.1 }}" class]{% endfor %} }];{% else %}responseArray = [self processResponseWithClass:[{{ name }} class]];{% endif %}
				self.responseData = nil;
				[self completeWithSelector:@selector({{ app_name_lower }}Connection:didRead{{ name_plural }}For{{ parent_name }}:) object:responseArray];
				[responseArray release];
				break;"""

CREATE_RELATED_RESPONSE = """
			case REQUEST_{{ app_name|upper }}_CREATE_{{ parent_name|upper }}_{{ name|upper }}:
				[tempRequestObject setObjectId:_newObjectId];
				self.responseData = nil;
				[self completeWithSelector:@selector({{ app_name_lower }}Connection:didCreate{{ name }}For{{ parent_name }}:) object:tempRequestObject];
				break;"""

READ_RELATED_OBJECT_RESPONSE = """
			case REQUEST_{{ app_name|upper }}_READ_{{ parent_name|upper }}_{{ name|upper }}:
				responseObject = [self processResponseWithClass:[{{ name }} class]];
				self.responseData = nil;
				[self completeWithSelector:@selector({{ app_name_lower }}Connection:didRead{{ name }}For{{ parent_name }}:) object:responseObject];
				[responseObject release];
				break;"""

UPDATE_RELATED_RESPONSE = """
			case REQUEST_{{ app_name|upper }}_UPDATE_{{ parent_name|upper }}_{{ name|upper }}:
				self.responseData = nil;
				[self completeWithSelector:@selector({{ app_name_lower }}Connection:didUpdate{{ name }}For{{ parent_name }}:) object:tempRequestObject];
				break;"""

class Command(BaseCommand, GenerateConnectionsCommand):
	help = 'Generate iOS connections for API endpoints.'
	option_list = BaseCommand.option_list + GenerateConnectionsCommand.option_list + (
			make_option('--connection',
				type='string',
				dest='connection',
				default='APIURLConnection',
				help='Connection class to use that should have the same interface as NSURLConnection.'),
		)

	def extra_context(self):
		return {'connection': self.connection }

	def handle(self, *args, **options):
		# Remember options
		self.connection = options['connection']

		# Create the templates
		self.templates = []
		template_path = os.path.join(os.path.normpath(os.path.dirname(__file__) + '/../templates'), 'ios-connection.h')
		with open(template_path) as f:
			self.templates.append(Template(f.read()))
		template_path = os.path.join(os.path.normpath(os.path.dirname(__file__) + '/../templates'), 'ios-connection.m')
		with open(template_path) as f:
			self.templates.append(Template(f.read()))
		self.template_extensions = ['h', 'm']

		# Create the mappings
		import_template = Template('#import "{{ name }}.h"')
		imports_mapping = dict.fromkeys(GenerateConnectionsCommand.ALL_ACTIONS, import_template)
		imports_mapping['RemoveDuplicates'] = True
		imports_mapping['Sort'] = True

		request_types_base = 'REQUEST_{{ app_name|upper }}_%s_%s'
		request_types_mapping = {
			'READ_OBJECT': Template(request_types_base % ('READ', '{{ name|upper }}')),
			'READ_LIST': Template(request_types_base % ('READ', '{{ name_plural|upper }}')),
			'CREATE': Template(request_types_base % ('CREATE', '{{ name|upper }}')),
			'UPDATE': Template(request_types_base % ('UPDATE', '{{ name|upper }}')),
			'DELETE': Template(request_types_base % ('DELETE', '{{ name|upper }}')),
			'READ_RELATED_LIST': Template(request_types_base % ('READ', '{{ parent_name|upper }}_{{ name_plural|upper }}')),
			'CREATE_RELATED': Template(request_types_base % ('CREATE', '{{ parent_name|upper }}_{{ name|upper }}')),
			'READ_RELATED_OBJECT': Template(request_types_base % ('READ', '{{ parent_name|upper }}_{{ name|upper }}')),
			'UPDATE_RELATED': Template(request_types_base % ('UPDATE', '{{ parent_name|upper }}_{{ name|upper }}')),
			'RemoveDuplicates': True,
			'Sort': True
		}

		delegate_method_decls_base = "- (void){{ app_name_lower }}Connection:({{ app_name }}Connection *)connection did%s;"
		delegate_method_decls_mapping = {
			'READ_OBJECT': Template(delegate_method_decls_base % ('Read{{ name }}:({{ name }} *){{ name_lower }}')),
			'READ_LIST': Template(delegate_method_decls_base % ('Read{{ name_plural }}:(NSArray *){{ name_plural_lower }}')),
			'CREATE': Template(delegate_method_decls_base % 'Create{{ name }}:({{ name }} *){{ name_lower }}'),
			'UPDATE': Template(delegate_method_decls_base % 'Update{{ name }}:({{ name }} *){{ name_lower }}'),
			'DELETE': Template(delegate_method_decls_base % 'Delete{{ name }}:({{ name }} *){{ name_lower }}'),
			'READ_RELATED_LIST': Template(delegate_method_decls_base % ('Read{{ name_plural }}For{{ parent_name }}:(NSArray *){{ name_plural_lower }}')),
			'CREATE_RELATED': Template(delegate_method_decls_base % ('Create{{ name }}For{{ parent_name }}:({{ name }} *){{ name_lower }}')),
			'READ_RELATED_OBJECT': Template(delegate_method_decls_base % ('Read{{ name }}For{{ parent_name }}:({{ name }} *){{ name_lower }}')),
			'UPDATE_RELATED': Template(delegate_method_decls_base % ('Update{{ name }}For{{ parent_name }}:({{ name }} *){{ name_lower }}')),
			'RemoveDuplicates': True,
			'Sort': True
		}

		method_decls_mapping = {
			'READ_OBJECT': Template('- (void)read{{ name }}%s;' % WITH_PARAM),
			'READ_LIST': Template('- (void)read{{ name_plural }};\n- (void)read{{ name_plural }}WithParams:(APIRequestParams *)params;'),
			'CREATE': Template('- (void)create{{ name }}:({{ name }} *){{ name_lower }};'),
			'UPDATE': Template('- (void)update{{ name }}:({{ name }} *){{ name_lower }};'),
			'DELETE': Template('- (void)delete{{ name }}:({{ name }} *){{ name_lower }};'),
			'READ_RELATED_LIST': Template('- (void)read{{ name_plural }}For{{ parent_name }}%s;\n- (void)read{{ name_plural }}For{{ parent_name }}%s;' % (WITH_PARENT_PARAM, WITH_PARENT_PARAM_PARAMS)),
			'CREATE_RELATED': Template('- (void)create{{ name }}%s:({{ name }} *){{ name_lower }}%s;' % (FOR_PARENT, FOR_PARENT_PARAM)),
			'READ_RELATED_OBJECT': Template('- (void)read{{ name }}For{{ parent_name }}%s;' % WITH_PARENT_PARAM),
			'UPDATE_RELATED': Template('- (void)update{{ name }}%s:({{ name }} *){{ name_lower }}%s;' % (FOR_PARENT, FOR_PARENT_PARAM)),
			'Sort': True
		}

		block_method_decls_mapping = {
			'READ_OBJECT': Template('- (void)read{{ name }}%s;' % WITH_PARAM_COMPLETION),
			'READ_LIST': Template('- (void)read{{ name_plural }}WithParams:(APIRequestParams *)params completionHandler:(APIListHandler)completion;'),
			'CREATE': Template('- (void)create{{ name }}:({{ name }} *){{ name_lower }} completionHandler:(APIHandler)completion;'),
			'UPDATE': Template('- (void)update{{ name }}:({{ name }} *){{ name_lower }} completionHandler:(APIHandler)completion;'),
			'DELETE': Template('- (void)delete{{ name }}:({{ name }} *){{ name_lower }} completionHandler:(APIHandler)completion;'),
			'READ_RELATED_LIST': Template('- (void)read{{ name_plural }}For{{ parent_name }}%s completionHandler:(APIListHandler)completion;' % WITH_PARENT_PARAM_PARAMS),
			'CREATE_RELATED': Template('- (void)create{{ name }}%s:({{ name }} *){{ name_lower }}%s completionHandler:(APIHandler)completion;' % (FOR_PARENT, FOR_PARENT_PARAM)),
			'READ_RELATED_OBJECT': Template('- (void)read{{ name }}For{{ parent_name }}%s;' % WITH_PARENT_PARAM_COMPLETION),
			'UPDATE_RELATED': Template('- (void)update{{ name }}%s:({{ name }} *){{ name_lower }}%s completionHandler:(APIHandler)completion;' % (FOR_PARENT, FOR_PARENT_PARAM)),
			'Sort': True
		}

		urls_mapping = {}
		urls_mapping['READ_OBJECT'] = Template('#define URL_{{ app_name|upper }}_{{ name|upper }}{% if param %}_WITH_{{ param|upper }}{% endif %} @"{{ url_format }}"')
		urls_mapping['READ_LIST'] = urls_mapping['CREATE'] = Template('#define URL_{{ app_name|upper }}_{{ name_plural|upper }} @"{{ url_format }}"')
		urls_mapping['UPDATE'] = urls_mapping['DELETE'] = Template('#define URL_{{ app_name|upper }}_{{ name|upper }} @"{{ url_format }}"')
		urls_mapping['READ_RELATED_LIST'] = urls_mapping['CREATE_RELATED'] = Template('#define URL_{{ app_name|upper }}_{{ parent_name|upper }}_{{ name_plural|upper }}{% if param %}_WITH_{{ param|upper }}{% endif %} @"{{ url_format }}"')
		urls_mapping['READ_RELATED_OBJECT'] = urls_mapping['UPDATE_RELATED'] = Template('#define URL_{{ app_name|upper }}_{{ parent_name|upper }}_{{ name|upper }}{% if param %}_WITH_{{ param|upper }}{% endif %} @"{{ url_format }}"')
		urls_mapping['RemoveDuplicates'] = True

		methods_mapping = {
			'READ_OBJECT': Template(READ_OBJECT_METHOD),
			'READ_LIST': Template(READ_LIST_METHOD),
			'CREATE': Template(CREATE_METHOD),
			'UPDATE': Template(UPDATE_METHOD),
			'DELETE': Template(DELETE_METHOD),
			'READ_RELATED_LIST': Template(READ_RELATED_LIST_METHOD),
			'CREATE_RELATED': Template(CREATE_RELATED_METHOD),
			'READ_RELATED_OBJECT': Template(READ_RELATED_OBJECT_METHOD),
			'UPDATE_RELATED': Template(UPDATE_RELATED_METHOD)
		}

		response_cases_mapping = {
			'READ_OBJECT': Template(READ_OBJECT_RESPONSE),
			'READ_LIST': Template(READ_LIST_RESPONSE),
			'CREATE': Template(CREATE_RESPONSE),
			'UPDATE': Template(UPDATE_RESPONSE),
			'DELETE': Template(DELETE_RESPONSE),
			'READ_RELATED_LIST': Template(READ_RELATED_LIST_RESPONSE),
			'CREATE_RELATED': Template(CREATE_RELATED_RESPONSE),
			'READ_RELATED_OBJECT': Template(READ_RELATED_OBJECT_RESPONSE),
			'UPDATE_RELATED': Template(UPDATE_RELATED_RESPONSE),
			'RemoveDuplicates': True
		}

		# Set the configuration options and render
		self.mappings = {'imports': imports_mapping, 'request_types': request_types_mapping, 'delegate_method_decls': delegate_method_decls_mapping, 'method_decls': method_decls_mapping, 'block_method_decls': block_method_decls_mapping, 'urls': urls_mapping, 'methods': methods_mapping, 'response_cases': response_cases_mapping }
		self.object_id_format = "%u"
		self.slug_format = "%@"
		self.object_id_type = "uint32_t"
		self.slug_type = "NSString *"
		self.render(*args, **options)
