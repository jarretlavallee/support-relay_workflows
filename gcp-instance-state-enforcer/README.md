# GCP Instance State Enforcer
This relay workflow enforces the state of all GCP instances in a project based on labels. Depending on the labels associated with the instance, it will start, stop, suspend, or resume the machine. Instances that are missing required labels will be stopped.

The current label set is below.


|*Name*|*Values*|*Format*|*Examples*|*Required*|*Default*|*Function*|
|------|--------|--------|----------|----------|---------|----------|
|owner|User name with underscores|String[1] Puppet User name replacing any dots by underscores|jarret_lavallee|Yes| |The name of who owns the machine|
|geo|amer, emea, apj|Enum[amer, emea, apj]|amer|Yes| |Used to determine which timezone the owner uses. The timezones are local to where the office is in each geo. apj: Asia/Singapore, emea: Europe/Belfast, amer: America/Los_Angeles|
|lifetime|indefinite, number[unit]|String[2] minute(m), hour(h), days(d), weeks(w)|e.g 1w,7d,24h,10m,indefinite|Yes| |Determine how long an instance should live. Currently only used to shut down the machine.|
|termination_date|year-month-day|String[5]|2021-12-01|No| |Give an end date for deleting an instance. This overrides other lifetime settings. Instances will eventually deleted 14 days after the termination date. Currently this only shuts the machine down.|
|runschedule|weekdays, daily, continuous|Enum[weekdays, daily, continuous]|daily|No|weekdays|When an instance should be running. It will be stopped when not in the `workhours` for the days. `weekdays` are Monday-Friday, `daily` is every day, and `continuous` machines run 24/7|
|workhours|starthour-endhour|Hour range 0 to 23|9-18|No|7-18|Which hours should the instance be on line for in 24 hour time. This is in the local time to the `geo`|
|autostart|true, false|Enum[true, false] Note this is a string|true|No|false|If the machine should be automatically started when it is in the correct `workhours`|
|shutdown_type|shutdown, suspend|Enum[shutdown, suspend]|suspend|No|shutdown|Weather to shut down or suspend the machine. Not available for E2 instances|
|stopped_until|year-month-day|String[5]| 2021-01-31|No| |An optional label to keep around offline. Use this for PTO or long absences|
|disabled |true, false|Enum[true, false] Note this is a string|true|No|false|An optional label that can be used to ensure the machine is stopped for extended time periods|

The basic logic is as follows.

1. Stop instance when `lifetime` has been exceeded
2. Stop instance when `termination_date` has past
3. Stop instance when not in `workinghours` based on `geo` and `runschedule` is `weekdays` or `daily`
4. Start instance when in `workinghours` based on `geo` and `autostart` is `true`
5. Stop instance on weekends when `runschedule` is weekdays
6. Do not Stop the instance when `runschedule` is continuous
7. Start currently stopped instances when `runschedule` is `continuous` and `autostart` is `true`
8. Do not start instances when `autostart` is `false`
9. Stop the instance when `stopped_until` has passed
10. Do not start the instance until the `stopped_until` has passed
11. Use `suspend` and `resume` operations when `shutdown_type` is `suspend`

Any machines that do no have a `owner`, `geo`, and `lifetime` label will automatically be stopped every hour. The defaults for a machine with those labels are to run during the weekdays in the local working hours. Outside of those hours, the machine will be shutdown and not automatically started.

To have a machine that is automatically started and stopped every weekday you would set the following labels.

* owner: my_name
* geo: emea
* lifetime: 2w
* autostart: true

To have a machine that runs 24/7 you can set labels like the following.

* owner: my_name
* geo: apj
* lifetime: 52w
* autostart: true
* runschedule: continuous

To have a machine that is suspended only on the weekends you can set labels like the following.

* owner: my_name
* geo: amer
* lifetime: 12w
* autostart: true
* runschedule: weekdays
* workhours: 0-23
* shutdown_type: suspend

To have a machine that is online from 7am to 7pm every day including weekends you can set labels like the following.

* owner: my_name
* geo: amer
* lifetime: 12w
* autostart: true
* runschedule: daily
* workhours: 7-19
