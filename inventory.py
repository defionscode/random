#!/usr/bin/env python
'''
This is the dynamic inventory script used for ITAM integration. It is smart
in that it uses a variety of logic to create proper groupings for Ansible
inventory to be used in Tower. In addition it supports the use of a meta-field
which permits the arbitrary creation of additional groups and additional
host_vars.

Example ITAM string:
"redacted_hostname,,RedHat Linux,Development,CBS,groups=Apache;T24;|webtype=reverse proxy;,,VMware Virtual Server,VMware-42 05 ,2015-05-19,,Available"

The meta field from the above string:
"groups=Apache;T24;|webtype=reverse proxy;"

This would create an inventory group 'Apache' and add the host to it. In
addition it would also add 'webtype' as a host_var to the host which would
allow for its use in a playbook/templates/etc

'''

import subprocess, json, os, sys, re

try:
    IMPORT_ENV = os.environ['IMPORT_ENV']
except KeyError:
    sys.exit('This dynamic inventory script requires the IMPORT_ENV'
             ' environment variable to be set in order to run')

if IMPORT_ENV not in ['Production', 'UAT', 'Lower']:
    sys.exit('The environment specified: %s, is not valid, it must be one of'
             ' UAT, Production, or Lower' % IMPORT_ENV)

try:
    ITAM_PATH = os.environ['ITAM_PATH']
except KeyError:
    sys.exit('This dynamic inventory script requires the ITAM_PATH'
             ' environment variable set to the path of the ITAM script')

ENV_MAPPINGS = dict(
    Production=['Production', 'DR'],
    UAT=['UAT'],
    Lower=['Development', 'QA']
)

groups_list = set()
meta_groups = set()

final_inventory = dict(
    _meta=dict(hostvars=dict())
    )



ITAM_CALL = subprocess.Popen([ITAM_PATH], stdout=subprocess.PIPE)
RAW_INV = ITAM_CALL.stdout.read()
INV_LIST = RAW_INV.split('\n')


def establish_groups_and_hostvars():
    '''
    Creates a list of groups to be created based on the ITAM strings returned
    and establishes the initial set of host_vars.
    '''

    for host in INV_LIST:
        try:
            hostname, globalzone, operating_system, env, business_unit, meta, description,\
            model, serial, install_date, chassis, lifecycle = host.split(',')

            if env in ENV_MAPPINGS[IMPORT_ENV]:
                datacenter = ''.join(list(hostname)[:4])
                groups_list.add(datacenter)
                groups_list.add(globalzone + '_zones')
                groups_list.add(operating_system)
                groups_list.add(business_unit)
                groups_list.add(model)

                if len(chassis.split(':')) > 1:
                    chassis = chassis.split(':')[0]
                    groups_list.add(chassis)
                else:
                    groups_list.add(chassis)

                potential_cluster = re.search(r'[a-bA-b]*$', hostname)
                if potential_cluster.group() is not '':
                    groups_list.add(hostname[:-1] + '_cluster')

                final_inventory['_meta']['hostvars'][hostname] = dict(globalzone=globalzone,
                                                                      operating_system=operating_system,
                                                                      env=env,
                                                                      Datacenter=datacenter,
                                                                      business_unit=business_unit,
                                                                      description=description,
                                                                      model=model,
                                                                      serial=serial,
                                                                      install_date=install_date,
                                                                      chassis=chassis,
                                                                      lifecycle=lifecycle,
                                                                      Membership=list())
                if meta and valid_meta(meta):
                    for itam_meta in meta.split('|'):
                        key, value = itam_meta.split('=')
                        if key.strip() == 'groups':
                            for group_name in value.split(';'):
                                if group_name:
                                    if group_name.endswith(';'):
                                        meta_groups.add(group_name[:-1])
                                    else:
                                        meta_groups.add(group_name)
                        elif len(value.split('=')) > 1:
                            hkey, hvar = value.split('=')
                            final_inventory['_meta']['hostvars'][hostname][hkey] = hvar
                        else:
                            final_inventory['_meta']['hostvars'][hostname][key] = value

        except ValueError:
            pass

def make_groups():
    '''Creates all inventory groups'''

    for group in groups_list:
        try:
            if group not in ['', '_zones']:
                final_inventory[group] = dict(hosts=list())
        except ValueError:
            pass
    for group in meta_groups:
        final_inventory[group] = dict(hosts=list())

def set_group_memberships():
    ''' This assigns particular hosts to groups'''

    for itam_host_line in INV_LIST:

        try:
            hostname, zone = itam_host_line.split(',')[:2]
            env = itam_host_line.split(',')[3]
            meta_str = itam_host_line.split(',')[5]

            if env in ENV_MAPPINGS[IMPORT_ENV]:
                for group in groups_list:
                    if group in itam_host_line and group not in ['', '_zones'] and 'zones' not in group:

                        final_inventory[group]['hosts'].append(hostname)

                        try:
                            final_inventory['_meta']['hostvars'][hostname]['Membership'].append(group)

                        except KeyError, badhost:
                            if len(itam_host_line.split(',')) > 12:
                                sys.exit("It seems %s has one or more commas"
                                         " in one of the ITAM fields, please"
                                         " check, fix, and try again" % badhost)

                    elif group == zone + '_zones' and zone != '' and group.split('_zones')[0] in itam_host_line:
                        final_inventory[group]['hosts'].append(hostname)
                        final_inventory['_meta']['hostvars'][hostname]['Membership'].append(group)

                    elif '_cluster' in group and group.split('_cluster')[0] in itam_host_line:
                        final_inventory[group]['hosts'].append(hostname)
                        final_inventory['_meta']['hostvars'][hostname]['Membership'].append(group)

                for group in meta_groups:

                    if group in meta_str and valid_meta(meta_str):
                        final_inventory[group]['hosts'].append(hostname)

                        try:
                            final_inventory['_meta']['hostvars'][hostname]['Membership'].append(group)
                        except KeyError, badhost:

                            if len(itam_host_line.split(',')) > 12:
                                sys.exit("It seems %s has one or more commas"
                                         " in one of the ITAM fields, please"
                                         " check, fix, and try again" % badhost)


        except ValueError:
            pass

def valid_meta(meta_string):
    '''
    This is intended for the meta-field string and does some sanity checks
    if standards are not followed then the meta-field is intentionally not
    parsed.
    '''

    bad_characters = [',']
    split_qty = len(meta_string.split('|'))

    if not '=' in meta_string:
        return False

    if meta_string.startswith(' ') or meta_string.endswith(' '):
        return False

    if any(char in meta_string for char in bad_characters):
        return False

    if not meta_string.startswith('groups='):
        return False

    if split_qty > 1:
        if not split_qty <= len(meta_string.split('=')):
            return False

    return True

def main():
    '''The function that calls everything else'''
    establish_groups_and_hostvars()
    make_groups()
    set_group_memberships()
    print json.dumps(final_inventory, indent=4)


if __name__ == '__main__':
    main()
