//
//  {{ prefix }}{{ name }}.m
//

#import "{{ prefix }}{{ name }}.h"
#import "API.h"

@implementation {{ prefix }}{{ name }}
{% if synthesizers %}{% for synthesize in synthesizers %}
{{ synthesize }}{% endfor %}
{% endif %}{% if default_values %}
- (id)init {
	if (self = [super init]) {
		// Default values {% for default_value_stmt in default_values %}
		{{ default_value_stmt }}{% endfor %}
	}
	return self;
}
{% endif %}
+ (instancetype){{ name_lower }} {
	return [[[{{ prefix }}{{ name }} alloc] init] autorelease];
}

- (id)initWithXMLData:(NSData *)data {
	{% if base_name %}if (self = [super initWithXMLData:data]){% else %}if (self = [super init]){% endif %} {
		[API parseXMLData:data intoObject:self];
	}
	return self;
}

- (id)initWithJSONData:(NSData *)data {
	NSDictionary *dictionary;
	NSError *error;
	if (NSClassFromString(@"NSJSONSerialization") == nil) {
		return nil;
	}
	dictionary = (NSDictionary *)[NSJSONSerialization JSONObjectWithData:data options:0 error:&error];
	if (self = [super init]) {
		[self setValuesForKeysWithDictionary:dictionary];
	}
	return self;
}

- (void)dealloc {% templatetag openbrace %}{% for dealloc_stmt in dealloc %}
	{{ dealloc_stmt }}{% endfor %}
	[super dealloc];
}

// Do not allow the default behavior of throwing NSUndefinedKeyException
- (void)setValue:(id)value forUndefinedKey:(NSString *)key {
	return;
}

// Set the default nil value for nullable-primitive fields to be 0, specifically non-included ForeignKeys
// Otherwise the default implementation will raise an exception when loading a null value for a ForeignKey
- (void)setNilValueForKey:(NSString *)key {
	[self setValue:@0 forKey:key];
}
{% if primary_field %}
- (uint32_t)objectId {
	return _{{ primary_field }};
}

- (void)setObjectId:(uint32_t)objectId {
	_{{ primary_field }} = objectId;
}

- (BOOL)isEqual:(id)other {
	{{ prefix }}{{ name }} *theOther;

	if (other == self) {
		return YES;
	}

	if (![other isKindOfClass:[{{ prefix }}{{ name }} class]]) {
		return NO;
	}

	theOther = ({{ prefix }}{{ name }} *)other;
	return _{{ primary_field }} == theOther->_{{ primary_field }};
}
{% endif %}{% if property_implementations %}{% for property_impl in property_implementations %}
{{ property_impl }}{% endfor %}{% endif %}{% for field, field_upper in datetime_fields %}
- (void)set{{ field_upper }}:(NSDate *)new{{ field_upper }} {
	new{{ field_upper }} = [API cleanDate:new{{ field_upper }}];
	if (_{{ field }} != new{{ field_upper }}) {
		[_{{ field }} release];
		_{{ field }} = [new{{ field_upper }} retain];
	}
}
{% endfor %}{% for setter in included_field_setters %}
{{ setter }}{% endfor %}
#pragma mark - Serialization methods

- (NSDictionary *)dictionary {
	NSMutableDictionary *dictionary = {% if base_name %}(NSMutableDictionary *)[super dictionary];{% else %}[NSMutableDictionary dictionary];{% endif %}
	NSArray *keys = @[{% for field in dict_fields %}@"{{ field }}"{% if not forloop.last %}, {% endif %}{% endfor %}];
	[dictionary addEntriesFromDictionary:[self dictionaryWithValuesForKeys:keys]];{% for include in dict_included %}
	{{ include }}{% endfor %}
	return dictionary;
}

- (NSDictionary *)jsonDictionary {
	NSMutableDictionary *dictionary = {% if base_name %}(NSMutableDictionary *)[super jsonDictionary];{% else %}[NSMutableDictionary dictionary];{% endif %}
	NSArray *keys = @[{% for field in dict_fields %}@"{{ field }}"{% if not forloop.last %}, {% endif %}{% endfor %}];
	[dictionary addEntriesFromDictionary:[self dictionaryWithValuesForKeys:keys]];{% for include in dict_included %}
	{{ include }}{% endfor %}{% for field, field_upper in datetime_fields %}
	if (_{{ field }}) {
		[dictionary setObject:[[API dateFormatter] stringFromDate:_{{ field }}] forKey:@"{{ field }}"];{% endfor %}
	}
	return dictionary;
}

- (NSData *)urlEncodedData {
	NSMutableArray *args = [NSMutableArray arrayWithCapacity:32];{% if base_name %}
	NSString *parentArgs = [[[NSString alloc] initWithData:[super urlEncodedData] encoding:NSUTF8StringEncoding] autorelease];
	[args addObject:parentArgs];{% endif %}{% for url_encoded_data_stmt in url_encoded_data %}
	{{ url_encoded_data_stmt }}{% endfor %}
	return [[args componentsJoinedByString:@"&"] dataUsingEncoding:NSUTF8StringEncoding];
}

- (NSData *)jsonData {
	NSError *error;
	if (NSClassFromString(@"NSJSONSerialization") == nil) {
		return nil;
	}
	return [NSJSONSerialization dataWithJSONObject:[self jsonDictionary] options:0 error:&error];
}

#pragma mark - NSCoding methods

- (void)encodeWithCoder:(NSCoder *)encoder {
	{% if base_name %}[super encodeWithCoder:encoder];{% endif %}{% for encode_stmt in encode %}
	{{ encode_stmt }}{% endfor %}
}

- (id)initWithCoder:(NSCoder *)decoder {
	{% if base_name %}if (self = [super initWithCoder:decoder]){% else %}if (self = [super init]){% endif %}
	{% templatetag openbrace %}{% for decode_stmt in decode %}
		{{ decode_stmt }}{% endfor %}
	}
	return self;
}

@end
