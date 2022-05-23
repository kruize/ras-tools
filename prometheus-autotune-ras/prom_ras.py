#!/usr/bin/python3

# imports
import getopt
import sys
import time
import requests
import validators
import subprocess
from shutil import which
from datetime import datetime, date
from prettytable import PrettyTable

# Constants

CMD_KUBECTL = "kubectl"
CMD_CURL = "curl"
DEFAULT_NAMESPACE = "default"


def usage():
    print("""
    USAGE:
        LONG:
            prom_ras.py --podname="<pod name>" --podsearch="<pod search>" --container=<container name> --duration="<time in sec> --url="<datasource url>""
        SHORT:
            prom_ras.py -p "<pod name>" -P "<pod search>" -c "<container name>" -t "<time in sec> -u "<datasource url>""
        
        OPTIONS:
            -h | --help         "Prints this message"
            -p | --podname      "Name of the pod"
            -P | --podsearch    "Name of pod to search (the first result will be taken as the pod name)"
            -c | --container    "Name of the container"
            -t | --duration     "Time duration to sleep in between the metric recordings"
            -u | --url          "URL of the datasource to query"
    """)
    exit()


def exit():
    print("Exiting Gracefully.")
    sys.exit(1)


def opt_check(opt: str, s_type: str):
    s_type = s_type.lower()
    # Not needed as params are strings but added to check strings in future by making params generic
    if s_type == "string" or s_type == "str":
        return isinstance(opt, str)
    if s_type == "number" or s_type == "integer" or s_type == "int":
        return opt.isnumeric()
    if s_type == "decimal" or s_type == "double" or s_type == "float":
        try:
            float(opt)
            return True
        except ValueError:
            return False


all_args = sys.argv

if len(all_args) < 2:
    print("Following args are required : POD NAME (or) POD SEARCH, DURATION (in secs), DATASOURCE URL")
    usage()

all_args = all_args[1:]

try:
    opts, args = getopt.getopt(
        all_args,
        "p:P:t:u:n:c:h",
        [
            "podname=",
            "podsearch=",
            "duration=",
            "url=",
            "namespace=",
            "container=",
            "help"
        ]
    )
except Exception as e:
    print("Error obtaining params - " + str(e))
    usage()

PODNAME = None
PODSEARCH = None
DURATION = None
DATASOURCE_URL = None
NAMESPACE = DEFAULT_NAMESPACE
CONTAINER = None

for opt, arg in opts:
    arg = arg.strip()
    if opt in ['-p', '--podname']:
        PODNAME = arg
    elif opt in ['-P', '--podsearch']:
        PODSEARCH = arg
    elif opt in ['t', '--duration']:
        if opt_check(arg, "int"):
            DURATION = int(arg)
        else:
            print("Invalid value for time duration. Please enter an numeric value for duration")
            usage()
    elif opt in ['-u', '--url']:
        if validators.url(arg):
            DATASOURCE_URL = arg
        else:
            print("Invalid datasource url. Please enter a valid url")
            usage()
    elif opt in ['-n', '--namespace']:
        NAMESPACE = arg
    elif opt in ['-c', '--container']:
        CONTAINER = arg
    elif opt in ['-h', '--help']:
        usage()

if PODNAME is not None and PODSEARCH is not None:
    print("""Warning: 
        Both POD NAME and POD SEARCH are given, Program considers POD NAME as primary and ignoring POD SEARCH""")

if PODNAME is not None and len(PODNAME) == 0:
    print("Invalid podname")
    exit()

if PODSEARCH is not None and len(PODSEARCH) == 0:
    print("Invalid pod search string")
    exit()

if CONTAINER is None or len(CONTAINER) == 0:
    print("Invalid container name")
    exit()


def check_installation(tool):
    if which(tool) is None:
        print("'" + tool + "' not installed. Please install '" + tool + "' and re-run the program")
        exit()


def check_prerequisites():
    check_installation(CMD_KUBECTL)
    check_installation(CMD_CURL)


def check_pod():
    global CMD_KUBECTL, NAMESPACE, PODNAME, PODSEARCH
    result = subprocess.Popen([CMD_KUBECTL, "-n", NAMESPACE, "get", "pods"], stdout=subprocess.PIPE)
    found_pod = False
    pods = []

    for line in result.stdout.readlines():
        # removes last 3 chars \n'
        podname = str(line).replace("b'", "")[:-3].split(" ")[0]
        if podname != "NAME":
            pods.append(podname)
        if podname == PODNAME:
            found_pod = True
            break
        if PODNAME is None and PODSEARCH is not None and podname.find(PODSEARCH) != -1:
            found_pod = True
            PODNAME = podname
            break

    if not found_pod:
        print("Invalid podname please try with a correct pod name")
        print("Available pods: " + str(pods))
        exit()


check_prerequisites()
check_pod()

cpu_mem_table = PrettyTable(["Timestamp", "Datasource", "CPU readings", "Memory Readings"])

kubectl_read_cpu_file = [
    CMD_KUBECTL,
    "-n",
    NAMESPACE,
    "exec",
    "-c",
    CONTAINER,
    PODNAME,
    "--",
    "cat",
    "/sys/fs/cgroup/cpu/cpuacct.usage_all"
]

kubectl_read_mem_file = [
    CMD_KUBECTL,
    "-n",
    NAMESPACE,
    "exec",
    "-c",
    CONTAINER,
    PODNAME,
    "--",
    "cat",
    "/sys/fs/cgroup/memory/memory.usage_in_bytes"
]

CPU_READING_NANO = 0
NANO_TO_SECS = 1000000000
CPU_READING = 0
MEM_READING_STR = ""
MEM_READING = 0


def record_cgroup_readings():
    global CPU_READING, MEM_READING, CPU_READING_NANO, NANO_TO_SECS, MEM_READING_STR, cpu_mem_table
    result = subprocess.Popen(kubectl_read_cpu_file, stdout=subprocess.PIPE)
    CPU_READING_NANO = 0
    for line in result.stdout.readlines():
        read_line = str(line).replace("b'", "")[:-3]
        parts = read_line.split(" ")
        if len(parts) == 3:
            if parts[1].isnumeric() and parts[2].isnumeric():
                CPU_READING_NANO = CPU_READING_NANO + int(parts[1]) + int(parts[2])

    CPU_READING = CPU_READING_NANO / NANO_TO_SECS

    result = subprocess.Popen(kubectl_read_mem_file, stdout=subprocess.PIPE)

    MEM_READING_STR = ""
    for line in result.stdout.readlines():
        read_line = str(line).replace("b'", "")[:-3]
        MEM_READING_STR = MEM_READING_STR + read_line

    MEM_READING = int(MEM_READING_STR)
    cpu_mem_table.add_row([datetime.now(), "Cgroup", CPU_READING, MEM_READING])


def curl_rec_query_cmd(query):
    return [
        CMD_CURL,
        "--silent",
        "--date-urlencode",
        query,
        DATASOURCE_URL
    ]


def record_prom_readings():
    cpu_query = {
        'query': 'container_cpu_usage_seconds_total{container="' + CONTAINER + '", image!="", pod="' + PODNAME + '"}'}
    mem_query = {
        'query': 'container_memory_working_set_bytes{container="' + CONTAINER + '", image!="", pod="' + PODNAME + '"}'}
    response = requests.get(DATASOURCE_URL, params=cpu_query)
    result = response.json()
    cpu_reading = float(result['data']['result'][0]['value'][1])
    response = requests.get(DATASOURCE_URL, params=mem_query)
    result = response.json()
    mem_reading = float(result['data']['result'][0]['value'][1])
    cpu_mem_table.add_row([datetime.now(), "Prometheus", cpu_reading, mem_reading])


print("First Reading - Recording Cgroup readings ...", end=" ")
record_cgroup_readings()
print("Done.")
print("First Reading - Recording Prometheus readings ...", end=" ")
record_prom_readings()
print("Done.")
print("Sleeping for " + str(DURATION) + " Seconds!")
time.sleep(DURATION)
print("Second Reading - Recording Cgroup readings ...", end=" ")
record_cgroup_readings()
print("Done.")
print("Second Reading - Recording Prometheus readings ...", end=" ")
record_prom_readings()
print("Done.")

print("CPU & Memory Recordings table :")
print(cpu_mem_table)

print("Calculating the min, max and mean from prometheus queries:")
print(
    'Memory Query - container_memory_working_set_bytes{container="' + CONTAINER + '", image!="", pod="' + PODNAME + '"}[' + str(
        DURATION) + 's]')

print(
    'Memory Min Query - min_over_time(container_memory_working_set_bytes{container="' + CONTAINER + '", image!="", pod="' + PODNAME + '"}[' + str(
        DURATION) + 's])')
print(
    'Memory Max Query - max_over_time(container_memory_working_set_bytes{container="' + CONTAINER + '", image!="", pod="' + PODNAME + '"}[' + str(
        DURATION) + 's])')
print(
    'CPU Query - container_cpu_usage_seconds_total{container="' + CONTAINER + '", image!="", pod="' + PODNAME + '"}[' + str(
        DURATION) + 's]')

print(
    'CPU Rate Query - rate(container_cpu_usage_seconds_total{container="' + CONTAINER + '", image!="", pod="' + PODNAME + '"}[' + str(
        DURATION) + 's])')


cpu_query = {
    'query': 'container_cpu_usage_seconds_total{container="' + CONTAINER + '", image!="", pod="' + PODNAME + '"}[' + str(
        DURATION) + 's]'}

cpu_rate_query = {
    'query': 'rate(container_cpu_usage_seconds_total{container="' + CONTAINER + '", image!="", pod="' + PODNAME + '"}[' + str(
        DURATION) + 's])'}

mem_query = {
    'query': 'container_memory_working_set_bytes{container="' + CONTAINER + '", image!="", pod="' + PODNAME + '"}[' + str(
        DURATION) + 's]'}

mem_min_query = {
    'query': 'min_over_time(container_memory_working_set_bytes{container="' + CONTAINER + '", image!="", pod="' + PODNAME + '"}[' + str(
        DURATION) + 's])'}

mem_max_query = {
    'query': 'max_over_time(container_memory_working_set_bytes{container="' + CONTAINER + '", image!="", pod="' + PODNAME + '"}[' + str(
        DURATION) + 's])'}

prom_table = PrettyTable(["Type", "Metric", "Min", "Max", "Mean"])

response = requests.get(DATASOURCE_URL, params=cpu_query)
result = response.json()
cpu_readings = result['data']['result'][0]['values']
rec_readings = [x[1] for x in cpu_readings]
diff_rec = [float(rec_readings[i + 1]) - float(rec_readings[i]) for i in range(len(rec_readings) - 1)]
rate_rec = [x/30 for x in diff_rec]
prom_table.add_row(["Calculated", "CPU", min(rate_rec), max(rate_rec), sum(rate_rec)/len(rate_rec)])
response = requests.get(DATASOURCE_URL, params=cpu_rate_query)
result = response.json()
prom_table.add_row(["Query", "CPU", "-", "-", result['data']['result'][0]['value'][1]])

response = requests.get(DATASOURCE_URL, params=mem_query)
result = response.json()
mem_raw_readings = result['data']['result'][0]['values']
mem_rec_readings = [int(x[1]) for x in mem_raw_readings]
prom_table.add_row(["Calculated", "Memory", min(mem_rec_readings), max(mem_rec_readings), sum(mem_rec_readings)/len(mem_rec_readings)])

response = requests.get(DATASOURCE_URL, params=mem_min_query)
result = response.json()
min_mem = result['data']['result'][0]['value'][1]

response = requests.get(DATASOURCE_URL, params=mem_max_query)
result = response.json()
max_mem = result['data']['result'][0]['value'][1]

prom_table.add_row(["Query", "Memory", min_mem, max_mem, "-"])

print(prom_table)

