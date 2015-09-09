#!/usr/bin/env python

import subprocess
import json
import os
import sys


try:
    import_env = os.environ['IMPORT_ENV']
except KeyError:
    sys.exit('This dynamic inventory script requires the IMPORT_ENV environment variable to be set in order to run')

if import_env not in ['Production', 'UAT', 'Lower']:
    sys.exit('The environment specified: %s, is not valid, it must be one of UAT, Production, or Lower' % import_env)

try:
    itam_path = os.environ['ITAM_PATH']
except KeyError:
    sys.exit('This dynamic inventory script requires the ITAM_PATH environment variable set to the path of the ITAM script')


groups_list = set()

final_inventory = dict(
    _meta = dict(hostvars = dict() )
    )

env_mappings = dict(
    Production = ['Production', 'DR'],
    UAT = ['UAT'],
    Lower = ['Development', 'QA']
)

itam_call = subprocess.Popen([itam_path], stdout=subprocess.PIPE)
raw_inv = itam_call.stdout.read()
inv_list = raw_inv.split('\n')


def establish_groups_and_hostvars():
    for host in inv_list:
        try:
            hostname, Globalzone, OS, Env, Business_Unit, Meta, Description, Model, Serial, Install_Date,Chassis,Lifecycle = host.split(',')
            if Env in env_mappings[import_env]:
                datacenter = ''.join(list(hostname)[:4])
                groups_list.add(datacenter)
                groups_list.add(Globalzone + '_zones')
                groups_list.add(OS)
    #            groups_list.add(Env)
                groups_list.add(Business_Unit)
                groups_list.add(Model)
    #            groups_list.add(Description)
    #            groups_list.add(Serial)
    #            groups_list.add(Install_Date)
                if len(Chassis.split(':')) > 1:
                    Chassis = Chassis.split(':')[0]
                    groups_list.add(Chassis)
                else:
                    groups_list.add(Chassis)
    #            groups_list.add(Lifecycle)

                final_inventory['_meta']['hostvars'][hostname] = dict(Globalzone=Globalzone,
                                                                  OS=OS,
                                                                  Env=Env,
                                                                  Datacenter=datacenter,
                                                                  Business_Unit=Business_Unit,
                                                                  Description=Description,
                                                                  Model=Model,
                                                                  Serial=Serial,
                                                                  Install_Date=Install_Date,
                                                                  Chassis=Chassis,
                                                                  Lifecycle=Lifecycle,
                                                                  Membership=list()
                                                              )
                if Meta and valid_meta(Meta):
                    for itam_meta in Meta.split('|'):
                        key, value = itam_meta.split('=')
                        if key.strip() == 'groups':
                            for group_name in value.split(';'):
                                if group_name:
                                    if group_name.endswith(';'):
                                        group_name.add(group_name[:-1])
                                    else:
                                        groups_list.add(group_name)
                        elif len(value.split('=')) > 1:
                            hkey, hvar = value.split('=')
                            final_inventory['_meta']['hostvars'][hostname][hkey] = hvar
                        else:
                            final_inventory['_meta']['hostvars'][hostname][key] = value

        except ValueError:
            pass

def make_groups():
    for group in groups_list:
        try:
            if group not in ['', '_zones']:
                final_inventory[group] = dict(hosts=list())
        except ValueError:
            pass

def set_group_memberships():
    for itam_host_line in inv_list:
        try:
            hostname, zone = itam_host_line.split(',')[:2]
            Env = itam_host_line.split(',')[3]

            if Env in env_mappings[import_env]:
                for group in groups_list:
                    if group in itam_host_line and group not in ['', '_zones'] and 'zones' not in group:
                        final_inventory[group]['hosts'].append(hostname)
                        try:
                            final_inventory['_meta']['hostvars'][hostname]['Membership'].append(group)
                        except KeyError, badhost:
                            if len(itam_host_line.split(',')) > 12:
                                sys.exit("It seems %s has one or more commas in one of the ITAM fields, please check, fix, and try again" % badhost)

                    if group == zone + '_zones' and zone != '' and group.split('_zones')[0] in itam_host_line:
                        final_inventory[group]['hosts'].append(hostname)
                        final_inventory['_meta']['hostvars'][hostname]['Membership'].append(group)

        except ValueError:
            pass

def valid_meta(meta_string):
    bad_characters = [' ', ',']

    split_qty = len(meta_string.split('|'))

    if any(char in meta_string for char in bad_characters):
        return False

    if not meta_string.startswith('groups='):
        return False

    if split_qty > 1:
        if not split_qty <= len(meta_string.split('=')):
            return False

    return True

def main():
    establish_groups_and_hostvars()
    make_groups()
    set_group_memberships()
    print json.dumps(final_inventory, indent=4)


if __name__ == '__main__':
    main()