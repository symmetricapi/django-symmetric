//
//  {{ name }}Connection.h
//

#import <Foundation/Foundation.h>
#import "API.h"
#import "APIRequestParams.h"{% for import in imports %}
{{ import }}{% endfor %}

enum {{ name }}RequestType : NSUInteger
{
	REQUEST_{{ name|upper }}_NONE,{% for request_type in request_types %}
	{{ request_type }}{% if not forloop.last %},{% endif %}{% endfor %}
};

typedef enum {{ name }}RequestType {{ name }}RequestType;

@class {{ name }}Connection;

@protocol {{ name }}ConnectionDelegate <NSObject>
@optional{% for delegate_method_decl in delegate_method_decls %}
{{ delegate_method_decl }}{% endfor %}
- (void){{ name_lower }}Connection:({{ name }}Connection *)connection requestFailed:(NSError *)error;
@end

@interface {{ name }}Connection : NSObject <NSURLConnectionDelegate, NSURLConnectionDataDelegate>

// After the request completes request type will be NONE and statusCode 0
// Special requestData must be maintained manually it is not set to nil upon completion or cancelation
@property (nonatomic, assign) id<{{ name }}ConnectionDelegate> delegate;
@property (nonatomic, readonly) {{ name }}RequestType requestType;
@property (nonatomic, readonly) NSUInteger statusCode;
@property (nonatomic, retain) APIRequestParams *requestParams;
@property (nonatomic, retain) NSData *requestData;

+ (instancetype)connection;
+ (instancetype)connectionWithDelegate:(id)delegate;
- (void)cancelCurrentRequest;
{% for method_decl in method_decls %}
{{ method_decl }}{% endfor %}
{% for block_method_decl in block_method_decls %}
{{ block_method_decl }}{% endfor %}

@end
