#!/usr/bin/python3

# imports
import getopt
import sys
import validators
import subprocess
from shutil import which

# Constants

CMD_KUBECTL = "kubectl"
CMD_CURL = "curl"
DEFAULT_NAMESPACE = "default"


def usage():
    print("""
    USAGE:
        LONG:
            prom_ras.py --podname="<pod name>" --podsearch="<pod search>" --duration="<time in sec> --url="<datasource url>""
        SHORT:
            prom_ras.py -p "<pod name>" -P "<pod search>" -t "<time in sec> -u "<datasource url>""
        
        OPTIONS:
            -h | --help         "Prints this message"
            -p | --podname      "Name of the pod"
            -P | --podsearch    "Name of pod to search (the first result will be taken as the pod name)"
            -t | --duration     "Time duration to sleep in between the metric recordings"
            -u | --url          "URL of the datasource to query"
    """)
    exit()


def exit():
    print("Exiting Gracefully.")
    sys.exit(1)


def opt_check(opt: str, type: str):
    type = type.lower()
    # Not needed as params are strings but added to check strings in future by making params generic
    if type == "string" or type == "str":
        return isinstance(opt, str)
    if type == "number" or type == "integer" or type == "int":
        return opt.isnumeric()
    if type == "decimal" or type == "double" or type == "float":
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
        "p:P:t:u:n:c",
        [
            "podname=",
            "podsearch=",
            "duration=",
            "url=",
            "namespace=",
            "container="
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


check_prerequisites()
result = subprocess.Popen([CMD_KUBECTL, "-n", NAMESPACE, "get", "pods"], stdout=subprocess.PIPE)
found_pod = False
pods = []
for line in result.stdout.readlines():
    # removes last 3 chars \n'
    podname = str(line).replace("b'","")[:-3].split(" ")[0]
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

print(PODNAME)