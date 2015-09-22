#!/usr/bin/python
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

DOCUMENTATION = '''
---
module: spacewalk_channels
version_added: "2.0"
short_description: update channels for a server via spacewalk
description:
     - Allows for the update of channels of a server via spacewalk
options:
  endpoint:
    description:
      - the endping for your spacewalk server
    required: true
  username:
    description:
      - Authentication username
    required: true
  password:
    description:
      - authentication password
    required: true
  channels:
    description:
      - A list of channels that the server should have
    required: true
  server_name:
    description:
      - the server name
    required: true
  append:
    description:
      - Whether to append only. By default this module will not remove any channels. Anything listed that isn't currently a channel will be added. Set to false or no if you want the ensure only the channels specified are present.
    required: false
    default: yes
    choices: [ "yes", "no" ]
author: "Jonathan I. Davila (@defionscode) <jdavila@ansible.com>"
'''

EXAMPLES = '''
- name: Spacewalk
 spacewalk_channels:
     endpoint: https://spacewalk.endpoint.com
     username: ansible
     password: password
     server_name: myserver 
     channels:
       - rhel-6.5-base
'''
import xmlrpclib
import json

def main():
    module = AnsibleModule(
        argument_spec=dict(
                      endpoint=dict(type='str', default=None, required=True),
                      username=dict(type='str', default=None, required=True),
                      password=dict(default=None, required=True, no_log=True),
                      channels=dict(type='list', default=None, required=True),
                      server_name=dict(type='str', default=None, required=True),
                      append=dict(type='bool', default=True, required=False)
                      )
    )

    ENDPOINT = module.params.get('endpoint')
    USERNAME = module.params.get('username')
    PASSWORD = module.params.get('password')
    CHANNELS = module.params.get('channels')
    SERVER   = module.params.get('server_name')
    APPEND   = module.params.get('append')

    changed=False
    space_conn = xmlrpclib.Server(ENDPOINT, verbose=0)
    key = space_conn.auth.login(USERNAME, PASSWORD)

    try:
        sysid = space_conn.system.getId(key, SERVER)[0]['id']
    except IndexError:
        module.fail_json(changed=False, msg="Insufficient Permissions for user %s on spacewalk" % USERNAME)

    current_channels = [channel['label'] for channel in space_conn.system.listSubscribedChildChannels(key, sysid)]
    if APPEND and CHANNELS != current_channels:
        if set(CHANNELS).issubset(current_channels):
            module.exit_json(changed=changed, server=SERVER, server_id=sysid, channels=CHANNELS)
        changed=True
        space_conn.system.setChildChannels(key, sysid, CHANNELS)
    elif not APPEND and CHANNELS != current_channels:
        changed=True
        space_conn.system.setChildChannels(key, sysid, CHANNELS)
    else:
        changed=False

    space_conn.auth.logout(key)

    module.exit_json(changed=changed, server=SERVER, server_id=sysid, channels=CHANNELS)


from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()
