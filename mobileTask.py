from context import Context 
import xml.etree.ElementTree as ET
from hierarchy import SemanticHierarchy
import logging
import copy
import json
from util import get_package_name
from infra import Event
import os
from os.path import join as pjoin
from setup import setup_app
import re
from typing import List, Tuple, Callable
import time
import joblib

artifact_root = "."

def get_test_tasks():
    # all_app_info = []
    # for test in getTestList():
    #     app = test["apk"].lower()
    #     target = test["function"]
    #     test_name = test['test'].__name__
    #     all_app_info.append({"app": app,  "target": target, "test_name": test_name})
    # with open("{artifact_root}/all_test_info.json", "w") as fp:
    #     json.dump(all_app_info, fp, indent=4)
    # print(f"{artifact_root}/all_test_info.json")
    with open(f"{artifact_root}/all_test_info.json", "r") as fp:
        all_app_info = json.load(fp)
    return all_app_info

def x_center_in_y(x:tuple,y:tuple):
    if x is None:
        return False
    "determine whether the centerpoint of bbox x is inside y"
    x_center_x = (x[0]+x[2])/2
    x_center_y = (x[1]+x[3])/2
    if x_center_x >= y[0] and x_center_x <= y[2] and x_center_y >= y[1] and x_center_y <= y[3]:
        return True 
    return False

def single_event_match(e,ground_truth_event,hierarchy):
    def filter_func(node):
        return x_center_in_y(parseBound(node.get('bounds')),parseBound(ground_truth_event['bounds']))
    required_nodes = [{'text':w.get('text'),'content-desc':w.get('content-desc'),'action':ground_truth_event['action']} for w in filter(filter_func,hierarchy.iter())]
    for event in required_nodes:
        if ((e['text'] == event['text'] and event['text'].strip(' ')!="") or (e['content-desc'] == event['content-desc'] and event['content-desc']!='')) and e['action']==event['action']:
            return True
    return False

def elem_equal(e1,e2):
    if e1['action'] == 'back' or e2['action'] == 'back':
        return False
    if e1['resource-id'] == e2['resource-id'] and e1['resource-id'] !='':
        return True
    if e1['text'] == e2['text'] and e1['text'].strip(' ')!='':
        return True
    if e1['content-desc'] == e2['content-desc'] and e1['content-desc']!='':
        return True
    if e1['class'] != e2['class']:
        return False
    return False        

def parseBound(bounds: str):
    if bounds is None:
        return None
    left_top, right_bot = bounds.split('][')
    x1, y1 = left_top[1:].split(',')
    x2, y2 = right_bot[:-1].split(',')
    return tuple(map(lambda x: int(x), [x1, y1, x2, y2]))


class MobileTestEnv():
    def __init__(self,port,task_info,baseline_name):
        # task_info: {"app": app,  "target": target, "test_name": test_name}
        self.contexts = []
        self.target = task_info['target']
        self.app= task_info['app']
        self.pkg = get_package_name(self.app)
        self.test_name = task_info['test_name']
        os.environ['ANDROID_SERIAL'] = port

        self.attempt_cnt = 0
        self.executed_events = []
        self.ground_truth_events = json.load(open(pjoin(f"{artifact_root}/test_cases_android12",self.test_name,"body.json"),'r'))
        
        self.termination_event = self.ground_truth_events[-1]

        self.controller.stop_app(self.pkg)
        self.controller.start_app(self.pkg)
        time.sleep(15)
        #setup_app(self.app)
        self.contexts.append(Context(self.controller.app_info()[1], self.target,
                       SemanticHierarchy(self.pkg, self.app, self.controller.dump(),
                                         self.controller.dump())))
        self.contexts:List[Context]
        self.baseline_name = baseline_name

    # WARNING: only works with android 12
    def evaluate(self):
        files = os.listdir(pjoin('test_cases_android12',f"{self.test_name}"))
        files = [f for f in files if f.endswith(".xml") and f.startswith('body')]
        files.sort(key = lambda x:int(x.split('.')[0][4:]))
        files.insert(0,'init.xml')

        needed = files[len(self.ground_truth_events) - 1]
        with open(pjoin('test_cases',f"{self.test_name}",needed),'r') as fp:
            hierarchy_str = fp.read()
        hierarchy = ET.fromstring(hierarchy_str)

        last_one = self.ground_truth_events[-1]
        for event in self.executed_events:
            if single_event_match(event,last_one, hierarchy):
                return 1.
        completion_all = len(self.ground_truth_events)
        complete_ones = 0
        for i, g in enumerate(self.ground_truth_events):
            needed = files[i]
            with open(pjoin('test_cases',f"{self.test_name}",needed),'r') as fp:
                hierarchy_str = fp.read()
            hierarchy = ET.fromstring(hierarchy_str)
            for event in self.executed_events:
                if single_event_match(event,g,hierarchy):
                    complete_ones += 1
                    break
        compl_rate = complete_ones/completion_all
        return  compl_rate
    
    def clone_state(self):
        return copy.deepcopy(self.contexts)
    
    def oracleTerminate(self,last_event:Event):
        if self.termination_event is not None and last_event is not None:
            if elem_equal(self.termination_event,last_event.dumpAsDict()):
                return True, 1.
        if self.attempt_cnt >= 15:
            return True, self.evaluate()   
        return False, 0 
    
    def step(self, action_response):
        self.attempt_cnt += 1

        if action_response == 'Init':
            current_context = self.contexts[-1]
            events = current_context.getEvents()
            elemDesc = [f"index-{i}: {x.dump()}" for i, x in enumerate(events)]
            observation_ = f"Currently we have {len(elemDesc)} widgets, namely:\n" + '\n'.join(elemDesc)
            
            return observation_, 0, False
        done = False
        observation_ = None
        logging.info(self.contexts)
        # observation, info = webshop_text(**self.sessions[session])
        
        event = self.parse_response(action_response,self.contexts[-1].getEvents())
        event.act(self.controller)
        self.executed_events.append(event.dumpAsDict())
        self.assure_in_app()
        current_context = Context(self.controller.app_info()[1], self.target,
                       SemanticHierarchy(self.pkg, self.app, self.controller.dump(),
                                         self.controller.dump()))
        events = current_context.getEvents()
        self.contexts.append(current_context)
        elemDesc = [f"index-{i}: {x.dump()}" for i, x in enumerate(events)]
        
        observation_ = f"Currently we have {len(elemDesc)} widgets, namely:\n" + '\n'.join(elemDesc)
        done, reward = self.oracleTerminate(event)
        
        #if done:
        #    self.uninstall_app()
            
        return observation_, reward, done
    
    def assure_in_app(self):
        if self.controller.app_info()[0] != self.pkg:
            self.controller.back()
            time.sleep(10)
        
        if self.controller.app_info()[0] != self.pkg:
            self.controller.stop_app(self.pkg)
            time.sleep(5)
            self.controller.start_app(self.pkg)
            time.sleep(15)
        
        if self.controller.app_info()[0] != self.pkg:
            print('critical error: restart app failed')
        return 
    def findFirstInteger(self, s: str):
        if re.search(r'\d+', s) is None:
            return None
        return int(re.search(r'\d+', s).group())
    
    def parse_response(self,response,events:List[Event],limit=lambda x: True)->Event:
        # prompt += "Please choose only one UI element with its index such that the element can make us closer to our test target."\
        #         + "\nIf none of the UI element can do so, respond with index-none."
        for m in re.finditer('index-', response):
            local = response[m.start():m.start()+12]
            if 'index-none' not in local and limit(self.findFirstInteger(local[5:])):
                index = self.findFirstInteger(local[5:])
                if index is not None and index < len(events):
                    return events[index]
        return Event.back()
        #if 'index-none' in response:
        #    return -1
        #raise NotImplementedError("How to deal with the situation where chatgpt cannot give any index?")
    def uninstall_app(self):
        self.controller.stop_app(self.pkg)
        return self.controller.device.app_uninstall(self.pkg)
    
    def save(self):
        
        os.makedirs(f"logs/{self.baseline_name}/{self.test_name}",exist_ok=True)  
        json.dump(self.executed_events,open(f"logs/{self.baseline_name}/{self.test_name}/event.json",'w'))
        joblib.dump(self.contexts,f"logs/{self.baseline_name}/{self.test_name}/context.pkl")
