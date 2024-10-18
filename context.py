from hierarchy import SemanticHierarchy, TotalVisibleHierarchy, VisibleHierarchy, Hierarchy
from typing import List, Tuple, Callable
from infra import TestCase, EventSeq, Oracle, Event, Widget
from configs import *
import util
import chatgpt
class Context:
    '''
    A context is a UI state maintains its own information as follows:
    - activity: the current activity
    - hierarchy: the processed hierarchy of the current activity, containing interactable UI actions and is used for UI state hashing.
    - bannedEvents: the disabled events based on domain knowledge.
    - event: the selected UI event in the UI state; do not allow repeated selection.
    '''
    hierarchy: Hierarchy
    activity: str
    bannedEvents = List[Event]
    target: str

    def __init__(self, activity: str, target: str, hierarchy: Hierarchy):
        self.target = target
        self.hierarchy = hierarchy
        self.activity = activity
        self.event = None
        self.bannedEvents = []
        self.initial_prompt = "Suppose you are an Android UI testing expert helping me write a UI test case. In our " \
                              "conversation, I will provide you with a list of UI elements with texts on the screen, " \
                              "and your task is to select the group of texts that are relevant to the test target.\n" \
                              f"Our testing target is to {self.target} and validate whether the app behaves correctly."

    def setRelevant(self):
        '''
        Filter textual information with rule-based heuristics or LLM-based heuristics.
        '''
        if INFODISTILL == InformationDistillationConf.CHATGPT:
            self.setTextRelevant()
            self.setContentDescRelevant()
        else:
            for w in self.hierarchy:
                w.contentDescRelevant = True if w.contentDesc.strip() != '' else False
                w.textRelevant = True if w.contentDescRelevant is not True else False
    def setTextRelevant(self):
        texts = list({w.text for w in self.hierarchy if w.text.strip() != ""})
        if len(texts) == 0:
            return

        textMapping = {t: set() for t in texts}
        for idx, w in enumerate(self.hierarchy):
            if w.text.strip() != "":
                textMapping[w.text].add(idx)
        interestingTextConsts = ["OFF", "ON"]
        if any([not util.isInteger(s) and s not in interestingTextConsts for s in texts]):
            interestingTexts = list(filter(lambda s: util.isInteger(s) or s in interestingTextConsts, texts))
            texts = list(filter(lambda s: not util.isInteger(s) and s not in interestingTextConsts, texts))
            elemTexts = [f"{idx}. " + m for idx, m in enumerate(texts)]

            description = f"Currently we have {len(elemTexts)} texts:\n" + '\n'.join(elemTexts)
            task = f"Remember that your task is to {self.target}. "
            prompt = '\n'.join([description, '', task])
            interestingTexts.extend([texts[idx] for idx in chatgpt.Session([('system', self.initial_prompt)]) \
                                    .queryListOfIndex(prompt, lambda x: x < len(texts))])
        else:
            interestingTexts = texts

        for text in interestingTexts:
            for i in textMapping[text]:
                self.hierarchy[i].textRelevant = True

    def setContentDescRelevant(self):
        descMapping = [(w.contentDesc, idx) for idx, w in enumerate(self.hierarchy) if w.contentDesc.strip() != '']
        if len(descMapping) == 0:
            return
        elemDescs = [f"{idx}. " + m[0] for idx, m in enumerate(descMapping)]

        description = f"Currently we have {len(elemDescs)} texts:\n" + '\n'.join(elemDescs)
        task = f"Remember that your task is to {self.target}. "
        prompt = '\n'.join([description, '', task])

        for idx in chatgpt.Session([('system', self.initial_prompt)]).queryListOfIndex(prompt,
                                                                                       lambda x: x < len(descMapping)):
            self.hierarchy[descMapping[idx][1]].contentDescRelevant = True
        for w in self.hierarchy:
            if "ImageButton" in w.clazz:
                w.contentDescRelevant = True

    def setEvent(self, event: Event):
        self.event = event

    # get all available events (remove banned ones)
    def getEvents(self) -> List[Event]:
        if INFODISTILL in [InformationDistillationConf.SCRIPT, InformationDistillationConf.CHATGPT]:
            events = self.hierarchy.getEvents()
            # TODO: add unique
            return list(filter(lambda x: x not in self.bannedEvents, events))
        raise NotImplementedError()

        # SHUFFLE
        # shuffle(events)

    def __eq__(self, other: "Context"):
        print('checking context equal')
        def isVisible(node):
            return all(node.get(p) == "true" for p in ['focusable', 'visible-to-user'])


        if self.activity is not None and other.activity is not None and self.activity != other.activity:
            print(self.activity, other.activity)
            return False

        ui_hash_set = {hash(widget) for widget in self.hierarchy}
        cur_hash_set = {hash(widget) for widget in other.hierarchy}
        #print(ui_hash_set, cur_hash_set)
        #print(list(map(lambda x: x.attrib, self.hierarchy)), list(map(lambda x: x.attrib, other.hierarchy)))
        print(len(ui_hash_set), len(cur_hash_set), len(cur_hash_set & ui_hash_set))
        if len(cur_hash_set & ui_hash_set) / len(cur_hash_set | ui_hash_set) > 0.8:
            print('context equal')
            print([w.dumpAsDict() for w in self.hierarchy])
            print([w.dumpAsDict() for w in other.hierarchy])
            return True
        else:
            return False

    def ban(self, event: Event):
        if event != Event.back():
            self.bannedEvents.append(event)

    def ban_current(self):
        self.ban(self.event)
        self.event = None

