//
//  {{ prefix }}{{ name }}.h
//

#import <Foundation/Foundation.h>{% for import in imports %}
{{ import }}{% endfor %}
{% if base_name %}
#import "{{ prefix }}{{ base_name }}.h"
{% endif %}
@interface {{ prefix }}{{ name }} : {% if base_name %}{{ prefix }}{{ base_name }}{% else %}NSObject{% endif %} <NSCoding>

@property (nonatomic, assign) uint32_t objectId;{% for property_decl in properties %}
{{ property_decl }}{% endfor %}{% if property_declarations %}
{% for property_decl in property_declarations %}
{{ property_decl }}{% endfor %}{% endif %}

+ (instancetype){{ name_lower }};

- (id)initWithXMLData:(NSData *)data;
- (id)initWithJSONData:(NSData *)data;

- (NSDictionary *)dictionary;
- (NSDictionary *)jsonDictionary;
- (NSData *)urlEncodedData;
- (NSData *)jsonData;

@end
