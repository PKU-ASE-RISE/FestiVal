import os
import csv
import configparser
from enum import Enum

HistoryConf = Enum('HistoryConf', ['SPLIT', 'ALL', 'NONE', 'PROCESSED'])
HISTORY: HistoryConf = HistoryConf.NONE

InformationDistillationConf = Enum('InformationDistillation', ['CHATGPT', 'SCRIPT', 'NONE'])
INFODISTILL: InformationDistillationConf = InformationDistillationConf.CHATGPT

GenerationConf = Enum('GenerationConf', ['INTERACTIVE', 'SELFPLANNING', 'ONEHOP','BACKTRACK',"STATICFDTREE","NOPRUNE",'NOBACKTRACK',"DFSBACKTRACK","LOCALBACKTRACK","GLOBALBACKTRACK"])
GENERATION: GenerationConf = GenerationConf.INTERACTIVE

def init():
    global dev_id, apk_dir, apk_info
    dev_id = os.environ.get('ANDROID_SERIAL', 'emulator-5554')

    config = configparser.ConfigParser()
    config.read('config.ini')

    with open(config['DEFAULT']['apkinfo.path']) as f:
        reader = csv.DictReader(f)
        apk_info = {line['apk_name']: {
                    'package': line['package_name'],
                    'username': line['username'],
                    'password': line['password'],
                    } for line in reader}
    apk_dir = config['DEFAULT']['apk.dir']
    
    
    global seed_test_dir
    seed_test_dir = config['DEFAULT']['seed.test.dir']


init()
