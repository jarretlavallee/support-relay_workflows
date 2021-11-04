#!/usr/bin/env python
## Origional source: https://raw.githubusercontent.com/puppetlabs/relay-workflows/master/gcp-instance-reaper/filter-instances.py

import datetime
from datetime import datetime as dt, timedelta
import re
import json
# zoneinfo requires Python 3.9+
import sys
if sys.version_info.major < 3 or sys.version_info.minor < 9:
    raise Exception("Must be using Python 3.9+")

from zoneinfo import ZoneInfo

from relay_sdk import Interface, Dynamic as D


relay = Interface()

# The `MINUTES_TO_WAIT` global variable is the number of minutes to wait for
# a termination_date label to appear for the GCP instance.
MINUTES_TO_WAIT = 5

# The Indefinite lifetime constant
INDEFINITE = ['indefinite', 'infinity', '0']

WORKHOURS_DEFAULT = (7, 18)
RUNSCHEDULE_DEFAULT = 'weekdays'

# Geo to timezone mappings
TIMEZONES = {
    "apj": "Asia/Singapore",
    "emea": "Europe/Belfast",
    "amer": "America/Los_Angeles"
}

# Label names (user-configurable)
TERMINATION_DATE_LABEL = 'termination_date'
LIFETIME_LABEL = 'lifetime'
AUTOSTART_LABEL = 'autostart'
SHUTDOWN_TYPE_LABEL = 'shutdown_type'
RUNSCHEDULE_LABEL = 'runschedule'
WORKHOURS_LABEL = 'workhours'
GEO_LABEL = 'geo'
DISABLED_LABEL = 'disabled'
STOPPED_UNTIL_LABEL = 'stopped_until'
REQUIRED_LABELS = json.loads(relay.get(D.requiredLabels))
TERMINATE_DAYS = relay.get(D.terminateDays)
INSTANCES = relay.get(D.instances)
LOG_LEVEL = relay.get(D.logLevel)

def verbose_log(msg):
    if LOG_LEVEL == 'verbose':
        print(msg)

def get_label(gcp_instance, label_name):
    """
    :param gcp_instance: a description of a GCP instance.
    :param label_name: A string of the key name you are searching for.

    This method returns None if the GCP instance currently has no tags
    or if the label is not found. If the tag is found, it returns the label
    value.
    """
    if 'labels' not in gcp_instance.keys() or gcp_instance['labels'] is None:
        return None

    return gcp_instance['labels'][label_name] if label_name in gcp_instance['labels'] else None

def timenow_with_utc():
    """
    Return a datetime object that includes the tzinfo for utc time.
    """
    time = dt.utcnow()
    time = time.replace(tzinfo=datetime.timezone.utc)
    return time

def parse_lifetime_value(lifetime_value):
    """
    :param lifetime_value: A string from your GCP instance.

    Return a match object if a match is found; otherwise, return the None from
    the search method.
    """
    search_result = re.search(r'^([0-9]+)(w|d|h|m|y)$', lifetime_value)
    if search_result is None:
        return None
    toople = search_result.groups()
    unit = toople[1]
    length = int(toople[0])
    return (length, unit)


def calculate_lifetime_delta(lifetime_tuple):
    """
    :param lifetime_match: Resulting regex match object from parse_lifetime_value.
    Check the value of the lifetime. If not indefinite convert the regex match from
    `parse_lifetime_value` into a timedelta.
    """
    try:
        length = lifetime_tuple[0]
        unit = lifetime_tuple[1]
    except Exception as e:
        raise ValueError('Invalid lifetime label tuple: "{0}" error: "{1}"'.format(lifetime_tuple,e))
    if unit is None:
        raise ValueError("Unable to parse the lifetime unit")
    if unit == 'w':
        return timedelta(weeks=length)
    elif unit == 'h':
        return timedelta(hours=length)
    elif unit == 'd':
        return timedelta(days=length)
    elif unit == 'm':
        return timedelta(weeks=length*5)
    elif unit == 'y':
        return timedelta(weeks=length*52)
    else:
        raise ValueError("Unable to parse the lifetime unit '{0}'".format(unit))

def get_iso_date(data):
    for fmt in (r'%Y-%m-%dT%H:%M:%S.%f%z', r'%Y-%m-%dT%H:%M:%S%z', r'%Y-%m-%d'):
        try:
            iso_date = dt.strptime(data, fmt)
            return iso_date.replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            pass
    raise ValueError('no valid date format found')

def is_weekday(current_date):
    return 0 <= current_date.weekday() <= 4

def is_time_between(begin_time, end_time, check_time=None):
    # If check time is not given, default to current UTC time
    check_time = check_time or timenow_with_utc().time()
    if begin_time < end_time:
        return check_time >= begin_time and check_time <= end_time
    else: # crosses midnight
        return check_time >= begin_time or check_time <= end_time

def is_current_worktime(worktime_match, geo, runschedule):
    """
    :param worktime_match: Resulting regex match object from validate_workhours_value.
    Check the current time is in the working hours.
    """
    runschedule = runschedule or RUNSCHEDULE_DEFAULT
    if runschedule.lower() == 'continuous':
        return True

    timezone = TIMEZONES[geo]
    starttime = datetime.time(worktime_match[0] % 24)
    endtime = datetime.time(worktime_match[1] % 24)
    current_tz_date = dt.now(ZoneInfo(timezone))
    if is_time_between(starttime, endtime, current_tz_date.time()):
        if runschedule.lower() == 'daily':
            return True
        elif runschedule.lower() == 'weekdays' and is_weekday(current_tz_date):
            return True
    return False

def get_workhours_times(workhours_value=None):
    """
    :param workhours_value: A string from your GCP instance.

    Return a match object if a match is found; otherwise, return the None from
    the search method.
    """
    if workhours_value is None:
        return WORKHOURS_DEFAULT

    search_result = re.search(r'^([0-9]+)-([0-9]+)$', workhours_value)
    if search_result is None:
        return None
    toople = search_result.groups()
    starthour = int(toople[0])
    endhour = int(toople[1])
    return (starthour, endhour)

def validate_lifetime_value(val):
    return val in INDEFINITE or parse_lifetime_value(val) is not None

def validate_geo_value(val):
    return val in TIMEZONES.keys()

def validate_workhours_value(val):
    return get_workhours_times(val) is not None

def validate_runschedule_value(val):
    return val in ['weekdays', 'daily', 'continuous']

def validate_autostart_value(val):
    return val in ['true', 'false']

def validate_disabled_value(val):
    return val in ['true', 'false']

def validate_shutdown_type_value(val):
    return val in ['shutdown', 'suspend']

def validate_owner_value(val):
    return bool(val and val.strip())

def validate_termination_date_value(val):
    try:
        return get_iso_date(val) is not None
    except Exception as e:
        return False

def validate_stopped_until_value(val):
    try:
        return get_iso_date(val) is not None
    except Exception as e:
        return False

def required_labels_present(gcp_instance):
    """
    :param gpc_instance: a resource representing a GCP instance

    This method returns a boolean based on if the labels associated with this
    instance are valid or not. Invalid instances will be terminated.
    """
    for label in REQUIRED_LABELS:
        if get_label(gcp_instance, label) is None:
            raise ValueError("Missing label '{0}'".format(label))
    return True

def validate_labels(gcp_instance):
    if 'labels' not in gcp_instance.keys() or gcp_instance['labels'] is None:
        raise Exception('No Labels defined')
    required_labels_present(gcp_instance)
    for label in gcp_instance['labels'].keys():
        if 'validate_{0}_value'.format(label) in globals():
            val = get_label(gcp_instance, label)
            if not globals()['validate_{0}_value'.format(label)](val):
               raise ValueError('Invalid {0} label value: "{1}"'.format(label, val))

def should_be_started(gcp_instance):
    """
    :param gcp_instance: a resource representing an GCP instance

    This method returns a boolean and a reason if the instance should be
    started.
    """
    autostart = get_label(gcp_instance, AUTOSTART_LABEL)
    if autostart is None or autostart.lower() != 'true':
        return (False, 'No configuration for starting')

    disabled = get_label(gcp_instance, DISABLED_LABEL)
    if disabled is not None and disabled.lower() == 'true':
        return (False, 'Disabled')

    validate_labels(gcp_instance)

    timenow = timenow_with_utc()
    runschedule = get_label(gcp_instance, RUNSCHEDULE_LABEL)
    workhours = get_label(gcp_instance, WORKHOURS_LABEL)
    geo  = get_label(gcp_instance, GEO_LABEL)

    launch_date = get_iso_date(gcp_instance['creationTimestamp'])
    lifetime = get_label(gcp_instance, LIFETIME_LABEL)
    if lifetime is not None and lifetime not in INDEFINITE:
        lifetime_match = parse_lifetime_value(lifetime)
        end_date = launch_date + calculate_lifetime_delta(lifetime_match)
        if end_date < timenow:
            return (False, 'Lifetime elapsed on {0}'.format(end_date.strftime('%Y-%m-%d')))

    if is_current_worktime(get_workhours_times(workhours), geo, runschedule):
        stopped_until = get_label(gcp_instance, STOPPED_UNTIL_LABEL)
        if stopped_until is not None:
            stop_date = get_iso_date(stopped_until)
            if stop_date < timenow:
                return (True, 'Within working hours')
        else:
            return (True, 'Within working hours')

    return (False, 'No conditions met to initiate start')

def get_termination_date(gcp_instance, wait_time=MINUTES_TO_WAIT):
    """
    :param gcp_instance: a resource representing an GCP instance
    :param wait_time: The number of minutes to wait for the 'termination_date'

    This method returns when a 'termination_date' is found and raises an
    exception and terminates the instance when the wait_time has passed. The
    method looks for the 'lifetime' key, parses it, and sets the
    'termination_date' on the instance. The 'termination_date' can be set
    directly on the instance, bypassing the steps to parse the lifetime key and
    allowing this to return. This returns the termination_date value and reason
    if action should be taken at a given time; otherwise, it returns None (e.g.,
    for unlimited lifetimes or no tags available yet).
    """
    launch_date = get_iso_date(gcp_instance['creationTimestamp'])
    timenow = timenow_with_utc()

    try:
        validate_labels(gcp_instance)
    except ValueError as e:
        if launch_date + timedelta(minutes=wait_time) < timenow:
            # Timed out waiting for a label, so go ahead and delete this instance.
            raise ValueError(e)
        return (None, 'Waiting for labels to propagate')

    disabled = get_label(gcp_instance, DISABLED_LABEL)
    if disabled is not None and disabled.lower() == 'true':
        return (timenow - timedelta(minutes=5), 'Disabled')

    stopped_until = get_label(gcp_instance, STOPPED_UNTIL_LABEL)
    if stopped_until is not None:
        stop_date = get_iso_date(stopped_until)
        if stop_date > timenow:
            return (timenow - timedelta(minutes=5), 'Stopped until {0}'.format(stop_date.strftime('%Y-%m-%d')))

    runschedule = get_label(gcp_instance, RUNSCHEDULE_LABEL)
    workhours = get_label(gcp_instance, WORKHOURS_LABEL)
    geo  = get_label(gcp_instance, GEO_LABEL)

    if not is_current_worktime(get_workhours_times(workhours), geo, runschedule):
        return (timenow - timedelta(minutes=5), 'Not within working hours')

    termination_date = get_label(gcp_instance, TERMINATION_DATE_LABEL)

    if termination_date is None:
        lifetime = get_label(gcp_instance, LIFETIME_LABEL)
        if lifetime in INDEFINITE:
            return (None, 'Indefinite lifetime')
        else:
            lifetime_match = parse_lifetime_value(lifetime)
            end_date = launch_date + calculate_lifetime_delta(lifetime_match)
            owner = get_label(gcp_instance, 'owner')
            return (end_date, '{0} lifetime expires at {1}. Owner {2}'.format(lifetime, end_date.strftime('%Y-%m-%d'), owner))
    elif termination_date in INDEFINITE:
        return (None, 'Indefinite lifetime')
    else:
        return (get_iso_date(termination_date), 'Scheduled for termination on {0}'.format(termination_date))

def get_shutdown(instance):
    if get_label(instance, SHUTDOWN_TYPE_LABEL) == 'suspend':
        action = 'Suspending'
        append_list = 'to_suspend'
    else:
        action = 'Stopping'
        append_list = 'to_terminate'
    return (append_list, action)

def get_start(instance):
    if instance['status'] == 'SUSPENDED':
        action = 'Resuming'
        append_list = 'to_resume'
    else:
        action = 'Starting'
        append_list = 'to_start'
    return (append_list, action)

def chunk_list(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def states_to_slack_block(states):
    """
    :param states a hash of the various states with instances and reasons

    Converts the states into a slack consumable block
    """
    blocks = []

    for state, instances in states.items():
        if not bool(instances):
            continue

        blocks.append({"type": "divider"})
        section_header = {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*{0}*".format(state.capitalize())
            },
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": "*Instance*"
                },
                {
                    "type": "mrkdwn",
                    "text": "*Reason*"
                }
            ]
        }
        blocks.append(section_header)

        for inst in chunk_list(list(instances.items()), 5):
            section = {
                "type": "section",
                "fields": []
            }
            for instance, reason in inst:
                section['fields'].append({
                    "type": "plain_text",
                    "text": instance
                })
                section['fields'].append({
                    "type": "plain_text",
                    "text": reason
                })
            blocks.append(section)

    return json.dumps(blocks)

if __name__ == '__main__':
    to_terminate = []
    to_suspend = []
    to_delete = []
    to_start = []
    to_resume = []
    states = {
        "deleting": {},
        "stopping": {},
        "suspending": {},
        "starting": {},
        "resuming": {},
        "expiring": {},
        "error": {}
    }

    running_instances = filter(lambda i: i['status'] == 'RUNNING', INSTANCES)
    timenow = timenow_with_utc()
    for instance in running_instances:
        try:
            (termination_date, reason) = get_termination_date(instance)
            if termination_date is not None:
                action = None
                if timenow > termination_date + timedelta(days=TERMINATE_DAYS):
                    # Expired for longer than 14 days
                    action = 'Deleting'
                    to_delete.append(instance)
                elif termination_date < timenow:
                    # Should be shut down
                    (append_list, action) = get_shutdown(instance)
                    locals()[append_list].append(instance)
                else:
                    if termination_date < timenow + timedelta(days=1):
                        # Instances expiring within 24 hours
                        action = 'Expiring'
                    else:
                        verbose_log('{0}: {1}'.format(instance['name'], reason))
                if action:
                    states[action.lower()][instance['name']] = reason
                    print('{0} {1}: {2}'.format(action, instance['name'], reason))
            else:
                verbose_log('{0} is running as expected: {1}'.format(instance['name'], reason))
        except Exception as e:
            (append_list, action) = get_shutdown(instance)
            locals()[append_list].append(instance)
            states['error'][instance['name']] = '{0}: {1}'.format(action, e)
            print('{0} {1} due to a processing error: {2}'.format(action, instance['name'], e))

    stopped_instances = filter(lambda i: i['status'] == 'TERMINATED' or i['status'] == 'SUSPENDED', INSTANCES)
    for instance in stopped_instances:
        try:
            (should_start, reason) = should_be_started(instance)
            if should_start:
                (append_list, action) = get_start(instance)
                locals()[append_list].append(instance)
                states[action.lower()][instance['name']] = reason
                print('{0} {1}: {2}'.format(action, instance['name'], reason))
            else:
                verbose_log('{0} is stopped as expected: {1}'.format(instance['name'], reason))
        except Exception as e:
            states['error'][instance['name']] = 'Not starting: {0}'.format(e)
            print('Not starting {0} due to a processing error: {1}'.format(instance['name'], e))

    relay.outputs.set('to_terminate', to_terminate)
    relay.outputs.set('to_suspend', to_suspend)
    relay.outputs.set('to_delete', to_delete)
    relay.outputs.set('to_start', to_start)
    relay.outputs.set('to_resume', to_resume)
    try:
        relay.outputs.set('slack_block', states_to_slack_block(states))
    except Exception as e:
        print('Unable to print slack_block: {0} , {1}'.format(states, e))
        block = '[{"type": "section","text": {"type": "mrkdwn","text": "Failed to generate slack block: {0}"}}]'.format(e)
        relay.outputs.set('slack_block', block)
