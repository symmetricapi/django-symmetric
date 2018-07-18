//
//  {{ name }}Connection.m
//

#import "{{ name }}Connection.h"{% if connection != "NSURLConnection" %}
#import "{{ connection }}.h"{% endif %}
#import "NSString+API.h"

{% for url in urls %}{{ url }}
{% endfor %}

#pragma mark - {{ name }}Connection

@interface {{ name }}Connection () {
	APIAction _action;
	uint32_t _newObjectId;
	{{ connection }} *_connection;
}

@property (nonatomic, retain) id requestObject;
@property (nonatomic, retain) NSMutableData *responseData;
@property (nonatomic, copy) APIHandler completionHandler;
@property (nonatomic, copy) APIReadHandler readHandler;
@property (nonatomic, copy) APIListHandler listHandler;

@end

@implementation {{ name }}Connection

#pragma mark - Internal request and response methods

// Completion methods will invoke the callback methods and will also cleanup the temporary blocks if set

- (void)completeWithError:(id)error {
	APIHandler completionHandler = _completionHandler;
	APIReadHandler readHandler = _readHandler;
	APIListHandler listHandler = _listHandler;
	NSError *apiError;

	if ([error isKindOfClass:[NSError class]]) {
		apiError = (NSError *)error;
	} else {
		apiError = [NSError errorWithMessage:(NSString *)error];
	}
	_completionHandler = nil;
	_readHandler = nil;
	_listHandler = nil;
	if ([_delegate respondsToSelector:@selector({{ name|lower }}Connection:requestFailed:)]) {
		[_delegate {{ name|lower }}Connection:self requestFailed:apiError];
	} else if (completionHandler) {
		completionHandler(apiError);
	} else if (readHandler) {
		readHandler(nil, apiError);
	} else if (listHandler) {
		listHandler(nil, apiError);
	}
	[completionHandler release];
	[readHandler release];
	[listHandler release];
}

- (void)completeWithSelector:(SEL)selector object:(id)obj {
	APIHandler completionHandler = _completionHandler;
	APIReadHandler readHandler = _readHandler;
	APIListHandler listHandler = _listHandler;

	_completionHandler = nil;
	_readHandler = nil;
	_listHandler = nil;
	if ([_delegate respondsToSelector:selector]) {
		[_delegate performSelector:selector withObject:obj];
	} else if (completionHandler) {
		completionHandler(nil);
	} else if (readHandler) {
		readHandler(obj, nil);
	} else if (listHandler) {
		listHandler(obj, nil);
	}
	[completionHandler release];
	[readHandler release];
	[listHandler release];
}

- (void)performRequestWithObject:(id)obj action:(APIAction)action requestType:({{ name }}RequestType)requestType path:(NSString *)path https:(BOOL)https login:(BOOL)loginRequired sign:(BOOL)sign {
	NSURLRequest *request;

	[self retain];

	// Clean up a current connection
	if (_connection != nil) {
		[_connection cancel];
		[self release];
	}
	_statusCode = 0;
	self.requestObject = nil;
	self.responseData = nil;

	if (_requestParams) {
		path = [NSString stringWithFormat:@"%@?%@", path, [_requestParams urlEncodedArgs]];
	}
	request = [API requestWithAction:action path:path data:[obj urlEncodedData] extraData:_requestData https:https sign:sign];
	_requestType = requestType;
	_connection = [{{ connection }} connectionWithRequest:request delegate:self loginRequired:loginRequired];
	if (_connection) {
		_action = action;
		self.requestObject = obj;
		self.responseData = [NSMutableData data];
	} else {
		[self completeWithError:STRING_API_BADCONNECTION];
		_requestType = REQUEST_{{ name|upper }}_NONE;
		[self release];
	}
}

- (id)processResponseWithClass:(Class)cls NS_RETURNS_RETAINED {
	if (_action == API_ACTION_LIST) {
		NSMutableArray *array;
		if ([API serializationType] == API_SERIALIZATION_JSON) {
			NSError *error;
			id obj;
			array = (NSMutableArray *)[[NSJSONSerialization JSONObjectWithData:_responseData options:NSJSONReadingMutableContainers error:&error] retain];
			for (NSUInteger index = 0; index < [array count]; ++index) {
				obj = [[cls alloc] init];
				[obj setValuesForKeysWithDictionary:[array objectAtIndex:index]];
				[array replaceObjectAtIndex:index withObject:obj];
				[obj release];
			}
		} else {
			array = [[NSMutableArray alloc] init];
			[API parseXMLData:_responseData intoArray:array withClass:cls];
		}
		return array;
	} else {
		id obj;
		if ([API serializationType] == API_SERIALIZATION_JSON) {
			obj = [[cls alloc] initWithJSONData:_responseData];
		} else {
			obj = [[cls alloc] initWithXMLData:_responseData];
		}
		return obj;
	}
}

// A mixed result set, currently JSON only
- (NSArray *)processResponseWithClasses:(NSDictionary *idsClasses) {
	NSError *error;
	Class cls
	id obj;
	NSDictionary *dict;
	NSMutableArray *array = (NSMutableArray *)[[NSJSONSerialization JSONObjectWithData:_responseData options:NSJSONReadingMutableContainers error:&error] retain];
	for (NSUInteger index = 0; index < [array count]; ++index) {
		dict = [array objectAtIndex:index];
		for (id idField in idsClasses) {
			if ([dict objectForKey:idField]) {
				cls = [idsClasses objectForKey:idField]
				break;
			}
		}
		obj = [[cls alloc] init];
		[obj setValuesForKeysWithDictionary:dict];
		[array replaceObjectAtIndex:index withObject:obj];
		[obj release];
	}
}

+ (instancetype)connection {
	{{ name }}Connection *connection = [[[{{ name }}Connection alloc] init] autorelease];
	return connection;
}

+ (instancetype)connectionWithDelegate:(id)delegate {
	{{ name }}Connection *connection = [[[{{ name }}Connection alloc] init] autorelease];
	connection.delegate = delegate;
	return connection;
}

- (void)dealloc {
	[_connection cancel];
	_connection = nil;
	[_requestObject release];
	[_responseData release];
	[_completionHandler release];
	[_readHandler release];
	[_listHandler release];
	[_requestParams release];
	[_requestData release];
	[super dealloc];
}

- (void)cancelCurrentRequest {
	BOOL activeConnection = (_connection != nil);
	[_connection cancel];
	_connection = nil;
	self.requestObject = nil;
	self.responseData = nil;
	self.completionHandler = nil;
	self.readHandler = nil;
	self.listHandler = nil;
	_requestType = REQUEST_{{ name|upper }}_NONE;
	_statusCode = 0;
	if (activeConnection) {
		[self release];
	}
}{% for method in methods %}
{{ method }}{% endfor %}

#pragma mark - {{ connection }}Delegate methods

- (void)connection:({{ connection }} *)connection didReceiveResponse:(NSURLResponse *)response {
	_statusCode = [(NSHTTPURLResponse *)response statusCode];
	if (_requestParams) {
		[_requestParams processResponse:(NSHTTPURLResponse *)response];
	}
	_newObjectId = [[[(NSHTTPURLResponse *)response allHeaderFields] objectForKey:@"X-New-Object-Id"] unsignedIntValue];
	[_responseData setLength:0];
}

- (void)connection:({{ connection }} *)connection didReceiveData:(NSData *)data {
	[_responseData appendData:data];
}

- (NSCachedURLResponse *)connection:({{ connection }} *)connection willCacheResponse:(NSCachedURLResponse *)cachedResponse {
	return cachedResponse;
}

- (void)connection:({{ connection }} *)connection didFailWithError:(NSError *)error {
	self.requestObject = nil;
	self.responseData = nil;
	_connection = nil;
	if ([API isNetworkAvailable]) {
		[self completeWithError:STRING_API_BADCONNECTION];
	} else {
		[self completeWithError:STRING_API_NOINTERNET];
	}
	_requestType = REQUEST_{{ name|upper }}_NONE;
	_statusCode = 0;
	[self release];
}

- (void)connectionDidFinishLoading:({{ connection }} *)connection {
	id tempRequestObject, responseObject;
	NSArray *responseArray;

	responseObject = nil;
	responseArray = nil;

	// Make a temp reference of the requestObject in case the callback reuses the connection to make a new request that would overwrite requestObject
	tempRequestObject = [_requestObject retain];
	self.requestObject = nil;
	_connection = nil;
	if (_statusCode >= 400) {
		NSError *error = [self processResponseWithClass:[NSError class]];
		self.responseData = nil;
		[self completeWithError:error];
		[error release];
	} else {
		switch (_requestType) {
{% for response_case in response_cases %}{{ response_case }}
{% endfor %}
			default:
				self.responseData = nil;
				break;
		}
	}
	_requestType = REQUEST_{{ name|upper }}_NONE;
	_statusCode = 0;
	[tempRequestObject release];
	[self release];
}

@end
