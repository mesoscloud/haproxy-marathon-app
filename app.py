#!/usr/bin/env python

"""Generate HAProxy configuration (using Marathon as a data source)"""

import logging
import os
import re
import sys

import jinja2
import kazoo.client
import requests
import sseclient

# These are the marathon events that we want to pay attention to.
SIGNIFICANT = [
    'failed_health_check_event',
    'health_status_changed_event',
    'unhealthy_task_kill_event',

    'status_update_event',
]


def main():

    host = os.getenv('HOST', '127.0.0.1')

    logging.basicConfig()

    zk = kazoo.client.KazooClient(hosts=host + ':2181')
    zk.start()

    marathon = host + ':8080'

    def update():
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

        try:
            zk.create("/haproxy/config", haproxy_cfg.encode('utf-8'), makepath=True)
            print("znode created", file=sys.stderr)
        except kazoo.exceptions.NodeExistsError:
            data, stat = zk.get("/haproxy/config")
            if haproxy_cfg != data.decode('utf-8'):
                stat = zk.set("/haproxy/config", haproxy_cfg.encode('utf-8'))
                print("znode updated: {0!r}".format(stat), file=sys.stderr)

    update()
    for event in sseclient.SSEClient('http://{0}/v2/events'.format(marathon)):
        if event.event.rstrip() in SIGNIFICANT:
            update()


if __name__ == '__main__':
    main()
