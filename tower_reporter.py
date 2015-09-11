#!/usr/bin/env python

"""
This script is to be leveraged by autosys in order to grab details from Ansible
Tower and send a report via email.

Metrics Gathered
30 Days of Data

Ansible Tower Version
Ansible Core Version
# Hosts in Inventory
License Limit
Average Execution Time Per Job (pct change)
Number of Job Runs (pct change)
Number of Successful Runs
Failures
Number of Total Failures (pct change)
     Where greater than 50pct of hosts failed (pct change)
     Where less than 50pct of hosts failed (pct change)

Number of Scheduled Job Failures (pct change)
     Where greater than 50pct of hosts failed (pct change)
     Where less than 50pct of hosts failed (pct change)

Number of Manual Job Failures (pct change)
     Where greater than 50pct of hosts failed (pct change)
     Where less than 50pct of hosts failed (pct change)

"""

import os, sys, json, datetime, ConfigParser, smtplib, tempfile, csv
from email.mime.text import MIMEText

import requests

requests.packages.urllib3.disable_warnings()

config=ConfigParser.ConfigParser()
config.read('tower_reporter.ini')

TOWER_ENDPOINT=config.get('Auth', 'TOWER_ENDPOINT')

if TOWER_ENDPOINT.endswith('/'):
    TOWER_ENDPOINT=TOWER_ENDPOINT + 'api/v1/'
else:
    TOWER_ENDPOINT=TOWER_ENDPOINT + '/api/v1/'

TOWER_USER=config.get('Auth', 'TOWER_USER')
TOWER_PASS=config.get('Auth', 'TOWER_PASS')
REPORT_CSV_PATH=config.get('Report', 'REPORT_CSV_PATH')

TODAY           = datetime.date.today()
LAST_MONTH      = TODAY - datetime.timedelta(days=30)
TWO_MONTHS_AGO  = LAST_MONTH - datetime.timedelta(days=30)

TODAY           = TODAY.strftime("%Y-%m-%d")
LAST_MONTH      = LAST_MONTH.strftime("%Y-%m-%d")
TWO_MONTHS_AGO  = TWO_MONTHS_AGO.strftime("%Y-%m-%d")
# try:
#     VERIFY_SSL=bool(config.get('Auth', 'VERIFY_SSL'))
# except Exception:
#     VERIFY_SSL=True

TO_EMAIL=config.get('Report', 'TO_EMAIL')
FROM_EMAIL=config.get('Report', 'FROM_EMAIL')

def percentage(part, whole):
    return 100 * float(part)/float(whole)

def get_change_metrics(l_month_qty, c_month_qty, total_qty=None):
    num_change = c_month_qty - l_month_qty

    if total_qty is None:
        pct_change = percentage(num_change, l_month_qty)
    else:
        pct_change = percentage(num_change, total_qty)

    return num_change, pct_change


def get_data(target):
    """Generic helper function to make a get request and return the json dump"""
    r = requests.get(TOWER_ENDPOINT + target, auth=(TOWER_USER, TOWER_PASS), verify=False)
    if r.status_code != 200:
        sys.exit('Bad Reponse from Tower Endpoint. Error: %s' % r.text)
    return r.json()


def get_static_data():
    """Grabs static data. Versions of core/Tower, the license limit and current host count"""
    config_data           = get_data('config')

    ansible_core_version  = config_data['ansible_version']
    ansible_tower_version = config_data['version']
    license_limit         = config_data['license_info']['instance_count']
    current_host_count    = config_data['license_info']['current_instances']

    return ansible_tower_version, ansible_core_version, license_limit, current_host_count


def get_gt_lt_50_metrics(data):
    gt_50_pct = 0
    lt_50_pct = 0

    for job in data['results']:

        job_id              = job['id']
        host_data           = get_data('jobs/%s/job_host_summaries/' % job_id)
        total_hosts         = host_data['count']
        succeeded_hosts     = len( [host for host in host_data['results'] if host['failed'] == False ])
        failed_hosts        = len( [host for host in host_data['results'] if host['failed'] == True ])

        # print job_id, succeeded_hosts, total_hosts
        if total_hosts != 0:
            if percentage(succeeded_hosts, total_hosts) > 50:
                gt_50_pct += 1

            else:
                lt_50_pct += 1

    return gt_50_pct, lt_50_pct

def get_job_data():
    current_month_all_data      = get_data('jobs/?started__gte=%s' % LAST_MONTH)
    last_month_all_data         = get_data('jobs/?started__gte=%s' % TWO_MONTHS_AGO)

    current_month_job_count     = current_month_all_data['count']
    last_month_job_count        = last_month_all_data['count']

    current_month_success_data  = get_data('jobs/?status=successful&started__gte=%s' % LAST_MONTH)
    current_month_failed_data   = get_data('jobs/?status=failed&started__gte=%s' % LAST_MONTH)

    last_month_success_data     = get_data('jobs/?status=successful&started__gte=%s;started__lte=%s' % (TWO_MONTHS_AGO, LAST_MONTH))
    last_month_failed_data      = get_data('jobs/?status=failed&started__gte=%s;started__lte=%s' % (TWO_MONTHS_AGO, LAST_MONTH))

    current_failures_count      = current_month_failed_data['count']
    last_failures_count         = last_month_failed_data['count']

    current_success_count       = current_month_success_data['count']
    last_success_count          = last_month_success_data['count']

    current_avg_duration        = get_duration_avg(current_month_all_data)
    last_avg_duration           = get_duration_avg(last_month_all_data)

    current_month_gt_50pct_success, current_month_lt_50pct_success \
    = get_gt_lt_50_metrics(current_month_all_data)

    last_month_gt_50pct_success, last_month_lt_50pct_success \
    = get_gt_lt_50_metrics(last_month_all_data)

    # print current_month_gt_50pct_success, current_month_lt_50pct_success
    # print last_month_gt_50pct_success, last_month_lt_50pct_success

    job_qty_change,       job_pct_change       = get_change_metrics(last_month_job_count, current_month_job_count)
    success_qty_change,   success_pct_change   = get_change_metrics(last_success_count, current_success_count, current_month_job_count)
    failure_qty_change,   failure_pct_change   = get_change_metrics(last_failures_count, current_failures_count, current_month_job_count)
    gt_50_qty_change,     gt_50_pct_change     = get_change_metrics(last_month_gt_50pct_success, current_month_gt_50pct_success)
    lt_50_qty_change,     lt_50_pct_change     = get_change_metrics(last_month_lt_50pct_success, current_month_lt_50pct_success)
    duration_avg_change,  duration_pct_change  = get_change_metrics(last_avg_duration, current_avg_duration)

    return current_month_job_count, job_qty_change, job_pct_change, current_success_count, current_failures_count,\
    success_qty_change, success_pct_change, \
    failure_qty_change, failure_pct_change, gt_50_qty_change, gt_50_pct_change, \
    lt_50_qty_change, lt_50_pct_change, last_month_gt_50pct_success, \
    current_month_gt_50pct_success, current_month_lt_50pct_success, current_avg_duration, \
    duration_avg_change, duration_pct_change


def get_duration_avg(data):
    duration_times  = [job['elapsed'] for job in data['results']]
    avg_duration    = sum(duration_times) / len(duration_times)
    return avg_duration


def generate_csv(**kwargs):
    fieldnames=[
                'Date', 'Ansible Tower Version', 'Ansible Core Version',
                'Number of Hosts', 'License Limit', 'License Slots Remaining',
                'Total Jobs Executed', 'Job Execution Qty Change',
                'Job Execution Pct Change', 'Total Successful Jobs', 'Successful Jobs Qty Change',
                'Successful Jobs Pct Change', 'Total Failed Jobs', 'Failed Jobs Qty Change',
                'Failed Jobs Pct Change', 'Failed Jobs with at least 50% success',
                'Qty Change of Failed Jobs with at least 50% success',
                'Pct Change of Failed Jobs with at least 50% success',
                'Failed Jobs with less than 50% success',
                'Qty Change of Failed Jobs with less than 50% success',
                'Pct Change of Failed Jobs with less than 50% success',
                'Current Average Duration', 'Change in Average Duration', 'Pct Change in Average Duration'
                ]

    csv_dict = {
                'Date': kwargs.pop('date'),
                'Ansible Tower Version': kwargs.pop('tower_version'),
                'Ansible Core Version': kwargs.pop('core_version'),
                'Number of Hosts': kwargs.pop('host_count'),
                'License Limit': kwargs.pop('license_limit'),
                'License Slots Remaining': kwargs.pop('remaining_slots'),
                'Total Jobs Executed': kwargs.pop('total_jobs'),
                'Job Execution Qty Change': kwargs.pop('jobs_qty_chg'),
                'Job Execution Pct Change': kwargs.pop('job_pct_chg'),
                'Total Successful Jobs': kwargs.pop('success_jobs'),
                'Successful Jobs Qty Change': kwargs.pop('success_qty_chg'),
                'Successful Jobs Pct Change': kwargs.pop('success_pct_chg'),
                'Total Failed Jobs': kwargs.pop('failed_jobs'),
                'Failed Jobs Qty Change': kwargs.pop('failed_qty_chg'),
                'Failed Jobs Pct Change': kwargs.pop('failed_pct_chg'),
                'Failed Jobs with at least 50% success': kwargs.pop('gt_50_qty'),
                'Qty Change of Failed Jobs with at least 50% success': kwargs.pop('gt_50_qty_chg'),
                'Pct Change of Failed Jobs with at least 50% success': kwargs.pop('gt_50_pct_chg'),
                'Failed Jobs with less than 50% success': kwargs.pop('lt_50_qty'),
                'Qty Change of Failed Jobs with less than 50% success': kwargs.pop('lt_50_qty_chg'),
                'Pct Change of Failed Jobs with less than 50% success': kwargs.pop('lt_50_pct_chg'),
                'Current Average Duration': kwargs.pop('avg_duration'),
                'Change in Average Duration': kwargs.pop('avg_duration_chg'),
                'Pct Change in Average Duration': kwargs.pop('avg_duration_pct_chg')
                }

    if not os.path.isfile(REPORT_CSV_PATH):
        with open(REPORT_CSV_PATH, 'wb') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow(csv_dict)

    else:
      with open(REPORT_CSV_PATH, 'a') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writerow(csv_dict)


def send_email(**data):
    email_tmpl = """
Ansible Tower Monthly Report
Date: {date}
Ansible Tower Version: {tower_version}
Hosts Managed: {host_count}
License Limit: {license_limit}
Remaining License Slots: {remaining_slots}\n\n\n
### 30 Day Job Run Report ###
Total Jobs Ran: {total_jobs}
>>> Change from previous month: {jobs_qty_chg} ({job_pct_chg})\n
Successful Job Runs: {success_jobs}
>>> Change from previous month: {success_qty_chg} ({success_pct_chg})\n
Failed Job Runs: {failed_jobs}
>>> Change from previous month: {failed_qty_chg} ({failed_pct_chg})
>>> Failures where at least 50% of hosts succeeded: {gt_50_qty}
>>>>>> Change from previous month: {gt_50_qty_chg} ({gt_50_pct_chg})\n
>>> Failures where more than 50% of hosts succeeded: {lt_50_qty}
>>>>>> Change from previous month: {lt_50_qty_chg} ({lt_50_pct_chg})\n
Average Job Run Duration: {avg_duration}
>>> Change from previous month: {avg_duration_chg} ({avg_duration_pct_chg})\n

"""
    email_body = email_tmpl.format(**data)

    msg = MIMEText(email_body)
    msg['Subject'] = '[ANSIBLE_TOWER] Monthly Report'
    msg['From'] = FROM_EMAIL
    msg['To'] = TO_EMAIL
    s = smtplib.SMTP('localhost', 1025)
    s.sendmail(FROM_EMAIL, [TO_EMAIL], msg.as_string())
    s.quit()

def main():
    tower_v, ansible_v, license_limit, host_count = get_static_data()

    current_month_job_count, job_qty_change, job_pct_change, current_success_count, current_failures_count,\
    success_qty_change, success_pct_change, \
    failure_qty_change, failure_pct_change, gt_50_qty_change, gt_50_pct_change, \
    lt_50_qty_change, lt_50_pct_change, last_month_gt_50pct_success, \
    current_month_gt_50pct_success, current_month_lt_50pct_success, current_avg_duration, \
    duration_avg_change, duration_pct_change = get_job_data()

    results = dict(
                   date=TODAY, tower_version=tower_v, core_version=ansible_v,
                   license_limit=license_limit, host_count=host_count, remaining_slots=(license_limit-host_count),
                   total_jobs=current_month_job_count, jobs_qty_chg=job_qty_change,
                   job_pct_chg=job_pct_change, success_jobs=current_success_count,
                   success_qty_chg=success_qty_change, success_pct_chg=success_pct_change,
                   failed_jobs=current_failures_count, failed_qty_chg=failure_qty_change,
                   failed_pct_chg=failure_pct_change, gt_50_qty=current_month_gt_50pct_success,
                   gt_50_qty_chg=gt_50_pct_change, gt_50_pct_chg=gt_50_pct_change,
                   lt_50_qty=current_month_lt_50pct_success, lt_50_qty_chg=lt_50_qty_change, lt_50_pct_chg=lt_50_pct_change,
                   avg_duration=current_avg_duration, avg_duration_chg=duration_avg_change,
                   avg_duration_pct_chg=duration_pct_change)

    generate_csv(**results)
    send_email(**results)

if __name__ == '__main__':
    main()
