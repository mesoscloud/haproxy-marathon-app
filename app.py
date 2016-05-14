#!/usr/bin/python -u
#
# Copyright (c) 2015 Peter Ericson <pdericson@gmail.com>
#
# Permission to use, copy, modify, and distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

"""Generate HAProxy configuration (using Marathon as a data source)"""

import json
import logging
import os
import re
import subprocess
import sys
import time

import jinja2
import kazoo.client


def main():

    host = os.getenv('HOST', '127.0.0.1')

    logging.basicConfig()

    zk = kazoo.client.KazooClient(hosts=host + ':2181')
    zk.start()

    #
    zk.ensure_path("/haproxy")
    try:
        zk.create("/haproxy/config", b"")
    except kazoo.exceptions.NodeExistsError:
        pass

    #
    marathon = host + ':8080'

    while True:
        apps = []

        p = subprocess.Popen(["curl", "-fsS", "http://%s/v2/apps" % marathon], stdout=subprocess.PIPE)
        assert p.wait() == 0

        appIds = [app['id'] for app in json.loads(p.stdout.read().decode('utf-8'))['apps']]

        for appId in appIds:
            p = subprocess.Popen(["curl", "-fsS", "http://%s/v2/apps%s" % (marathon, appId)], stdout=subprocess.PIPE)
            assert p.wait() == 0

            app = json.loads(p.stdout.read().decode('utf-8'))['app']

            if 'portMappings' not in app['container']['docker']:
                continue

            apps.append(app)

        #
        def regex_replace(string, pattern, repl):
            return re.sub(pattern, repl, string)

        environment = jinja2.Environment()
        environment.filters['regex_replace'] = regex_replace

        with open('files/haproxy.cfg.j2') as f:
            x = f.read()
        template = environment.from_string(x)

        haproxy_cfg = template.render(apps=apps, host=host)
        haproxy_cfg = re.sub(r'\n{2,}', '\n\n', haproxy_cfg).rstrip() + '\n'

        data, stat = zk.get("/haproxy/config")

        if haproxy_cfg != data.decode('utf-8'):
            print("set", file=sys.stderr)
            zk.set("/haproxy/config", haproxy_cfg.encode('utf-8'))
        time.sleep(10)


if __name__ == '__main__':
    main()
