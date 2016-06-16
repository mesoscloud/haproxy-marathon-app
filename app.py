#!/usr/bin/env python

"""Generate HAProxy configuration (using Marathon as a data source)"""

import logging
import os
import re
import sys
import time

import jinja2
import kazoo.client
import requests


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

        r = requests.get("http://%s/v2/apps" % marathon)
        r.raise_for_status()

        appIds = [app['id'] for app in r.json()['apps']]

        for appId in appIds:
            r = requests.get("http://%s/v2/apps%s" % (marathon, appId))
            r.raise_for_status()

            app = r.json()['app']

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

        haproxy_cfg = template.render(apps=apps)
        haproxy_cfg = re.sub(r'\n{2,}', '\n\n', haproxy_cfg).rstrip() + '\n'

        data, stat = zk.get("/haproxy/config")

        if haproxy_cfg != data.decode('utf-8'):
            print("set", file=sys.stderr)
            zk.set("/haproxy/config", haproxy_cfg.encode('utf-8'))
        time.sleep(10)


if __name__ == '__main__':
    main()
