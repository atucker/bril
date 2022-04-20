import sys
import json

#print("Text");

print(json.dumps(json.load(sys.stdin)), flush=True)