#!/usr/bin/env python

"""
This script is to be leveraged by autosys in order to grab details from Ansible
Tower and send a report via email.

### SAMPLE REPORT ###
Ansible Tower Report
Date: 2015-09-12
Ansible Tower Version: 2.2.0
Hosts Managed: 18
License Limit: 10000
Remaining License Slots: 9982



### 5 Day Job Run Report ###
Total Jobs Ran: 26
>>> Change from previous 5 day range: 7 (36.84%)

Successful Job Runs: 18
>>> Change from previous 5 day range: 5 (19.23%)

Failed Job Runs: 7
>>> Change from previous 5 day range: 1 (3.85%)
>>> Failures where at least 50% of hosts succeeded: 15
    >>> Change from previous 5 day range: 6 (66.67%)

>>> Failures where less than 50% of hosts succeeded: 5
    >>> Change from previous 5 day range: 4 (400.0%)

Average Job Run Duration: 64.14 seconds
>>> Change from previous 5 day range: 34.22 seconds (114.37%)

"""

import os, sys, json, datetime, ConfigParser, smtplib, tempfile, csv
from email.mime.text import MIMEText

try:
    import requests
except ImportError:
    sys.exit('You must install python-requests to use this. Try'
             'pip install requests.')

requests.packages.urllib3.disable_warnings()

config = ConfigParser.ConfigParser()
config.read('tower_reporter.ini')

TOWER_ENDPOINT = config.get('Auth', 'TOWER_ENDPOINT')

if TOWER_ENDPOINT.endswith('/'):
    TOWER_ENDPOINT = TOWER_ENDPOINT + 'api/v1/'
else:
    TOWER_ENDPOINT = TOWER_ENDPOINT + '/api/v1/'

TOWER_USER      = config.get('Auth', 'TOWER_USER')
TOWER_PASS      = config.get('Auth', 'TOWER_PASS')
REPORT_CSV_PATH = config.get('Report', 'REPORT_CSV_PATH')

if config.get('Report', 'REPORT_RANGE') is not None:
    REPORT_RANGE = int(config.get('Report', 'REPORT_RANGE'))
else:
    REPORT_RANGE = 30

if config.get('Report', 'SMTP_PORT') is not None:
    SMTP_PORT = int(config.get('Report', 'SMTP_PORT'))
else:
    SMTP_PORT = 25

TODAY            = datetime.date.today()
LAST_PERIOD      = TODAY - datetime.timedelta(days=REPORT_RANGE)
TWO_PERIODS_AGO  = LAST_PERIOD - datetime.timedelta(days=REPORT_RANGE)

TODAY            = TODAY.strftime("%Y-%m-%d")
LAST_PERIOD      = LAST_PERIOD.strftime("%Y-%m-%d")
TWO_PERIODS_AGO  = TWO_PERIODS_AGO.strftime("%Y-%m-%d")

TO_EMAIL         = config.get('Report', 'TO_EMAIL')
FROM_EMAIL       = config.get('Report', 'FROM_EMAIL')

def percentage(part, whole):
    """Get a Percentage in Float format"""
    return float(format(100 * float(part)/float(whole), '.2f'))


def get_change_metrics(l_month_qty, c_month_qty, total_qty=None):
    """
    Simple funciton to provide the quantitative change and percentage between
    two numbers and an optional base number. If no basenumber is provided then
    l_month_qty is used as the base
    """
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
    """Fuction for retrieving 50% type data for failures/successes"""
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

            elif percentage(failed_hosts, total_hosts) > 50:
                lt_50_pct += 1
    return gt_50_pct, lt_50_pct

def get_job_data():
    """This is the meat of the script. Gets all the proper data and parses it"""
    current_month_all_data      = get_data('jobs/?started__gte=%s' % LAST_PERIOD)
    last_month_all_data         = get_data('jobs/?started__gte=%s;started__lte=%s' % (TWO_PERIODS_AGO, LAST_PERIOD))

    current_month_job_count     = current_month_all_data['count']
    last_month_job_count        = last_month_all_data['count']

    current_month_success_data  = get_data('jobs/?status=successful&started__gte=%s' % LAST_PERIOD)
    current_month_failed_data   = get_data('jobs/?status=failed&started__gte=%s' % LAST_PERIOD)

    last_month_success_data     = get_data('jobs/?status=successful&started__gte=%s;started__lte=%s' % (TWO_PERIODS_AGO, LAST_PERIOD))
    last_month_failed_data      = get_data('jobs/?status=failed&started__gte=%s;started__lte=%s' % (TWO_PERIODS_AGO, LAST_PERIOD))

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
    """Simple function to get duration averages"""
    duration_times  = [job['elapsed'] for job in data['results']]
    avg_duration    = sum(duration_times) / len(duration_times)
    return float(format(avg_duration, '.2f'))


def generate_csv(**kwargs):
    """Generates a CSV file to the config defined path. It will append the latest report if the CSV already exists."""
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

            try:
                writer.writeheader()
            except AttributeError:
                if csvfile.Sniffer.has_header():
                    csvfile.write(','.join(fieldnames) + '\n')

            writer.writerow(csv_dict)

    else:
      with open(REPORT_CSV_PATH, 'a') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writerow(csv_dict)


def send_email(**data):
    """Sends an email report"""
    email_tmpl = """
Ansible Tower Report
Date: {date}
Ansible Tower Version: {tower_version}
Hosts Managed: {host_count}
License Limit: {license_limit}
Remaining License Slots: {remaining_slots}\n\n\n
### {range} Day Job Run Report ###
Total Jobs Ran: {total_jobs}
>>> Change from previous {range} day range: {jobs_qty_chg} ({job_pct_chg}%)\n
Successful Job Runs: {success_jobs}
>>> Change from previous {range} day range: {success_qty_chg} ({success_pct_chg}%)\n
Failed Job Runs: {failed_jobs}
>>> Change from previous {range} day range: {failed_qty_chg} ({failed_pct_chg}%)
>>> Failures where at least 50% of hosts succeeded: {gt_50_qty}
    >>> Change from previous {range} day range: {gt_50_qty_chg} ({gt_50_pct_chg}%)\n
>>> Failures where less than 50% of hosts succeeded: {lt_50_qty}
    >>> Change from previous {range} day range: {lt_50_qty_chg} ({lt_50_pct_chg}%)\n
Average Job Run Duration: {avg_duration} seconds
>>> Change from previous {range} day range: {avg_duration_chg} seconds ({avg_duration_pct_chg}%)\n

"""
    email_body = email_tmpl.format(range=REPORT_RANGE, **data)

    msg = MIMEText(email_body)
    msg['Subject'] = '[ANSIBLE_TOWER] %s Day Report' % REPORT_RANGE
    msg['From'] = FROM_EMAIL
    msg['To'] = TO_EMAIL
    s = smtplib.SMTP('localhost', SMTP_PORT)
    s.sendmail(FROM_EMAIL, [TO_EMAIL], msg.as_string())
    s.quit()

def main():
    """Main function that runs everything else"""

    tower_v, ansible_v, license_limit, host_count = get_static_data()

    current_month_job_count, job_qty_change, job_pct_change, current_success_count, current_failures_count,\
    success_qty_change, success_pct_change, \
    failure_qty_change, failure_pct_change, gt_50_qty_change, gt_50_pct_change, \
    lt_50_qty_change, lt_50_pct_change, last_month_gt_50pct_success, \
    current_month_gt_50pct_success, current_month_lt_50pct_success, current_avg_duration, \
    duration_avg_change, duration_pct_change = get_job_data()

    results = dict(
                   date                   = TODAY,
                   tower_version          = tower_v,
                   core_version           = ansible_v,
                   license_limit          = license_limit,
                   host_count             = host_count,
                   remaining_slots        = (license_limit - host_count),
                   total_jobs             = current_month_job_count,
                   jobs_qty_chg           = job_qty_change,
                   job_pct_chg            = job_pct_change,
                   success_jobs           = current_success_count,
                   success_qty_chg        = success_qty_change,
                   success_pct_chg        = success_pct_change,
                   failed_jobs            = current_failures_count,
                   failed_qty_chg         = failure_qty_change,
                   failed_pct_chg         = failure_pct_change,
                   gt_50_qty              = current_month_gt_50pct_success,
                   gt_50_qty_chg          = gt_50_qty_change,
                   gt_50_pct_chg          = gt_50_pct_change,
                   lt_50_qty              = current_month_lt_50pct_success,
                   lt_50_qty_chg          = lt_50_qty_change,
                   lt_50_pct_chg          = lt_50_pct_change,
                   avg_duration           = current_avg_duration,
                   avg_duration_chg       = duration_avg_change,
                   avg_duration_pct_chg   = duration_pct_change)

    generate_csv(**results)
    send_email(**results)

if __name__ == '__main__':
    main()
