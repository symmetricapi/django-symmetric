import random
from optparse import make_option

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Obfuscate specified settings, keys, secrets etc. for use in mobile apps.'
    option_list = BaseCommand.option_list + (
        make_option(
            '--ios',
            action='store_true',
            dest='ios',
            default=False,
            help='Output obfuscated iOS code.',
        ),
        make_option(
            '--android',
            action='store_true',
            dest='android',
            default=False,
            help='Output obfuscated Android code.',
        ),
    )

    def handle(self, *args, **options):
        random.seed(None)
        for arg in args:
            if hasattr(settings, arg):
                setting = getattr(settings, arg)
                x = random.randint(0, 255)
                bytes = map(lambda b: hex(ord(b) ^ x), [ch for ch in setting])
                if options['ios']:
                    print "%s: [API deobfuscate:(unsigned char []){%s,0} size:%d x:%s]" % (arg, ','.join(bytes), len(bytes) + 1, hex(x))
                elif options['android']:
                    print "%s: API.deobfuscate(new byte[] {(byte)%s}, %s)" % (arg, ',(byte)'.join(bytes), hex(x))
