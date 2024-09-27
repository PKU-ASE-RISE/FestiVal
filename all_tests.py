import sys, inspect, shutil
import traceback
from typing import Type, Dict

import util
from pathlib import Path
from infra import Event, EventSeq, Oracle, Widget, RawHierarchy, TestCase
from setup import setup_app, uninstall_app
from util import *
from hierarchy import parseUIHierarchy
from screen_control import AndroidController

def save_json(path, js):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(js, f)

def save_current_json(path):
    save_json(path, parseUIHierarchy(get_current_ui()))

def save_ui(path):
    os.system("cp hierarchy.xml " + path)


"""
basic infras
"""

RESOURCEID = 'resource-id'
CONTENTDESC = 'content-desc'
TEXT = "text"
CLASS = "class"
BOUNDS = "bounds"

CLICK = "click"
BACK = "back"
TEXT = "text"
SWIPE = "swipe"

class Test:
    controller: AndroidController
    events: EventSeq = EventSeq()
    savePath: Path
    lastStage: str
    sizeCnt: dict = {}

    def __init__(self, port: str = "emulator-5554"):
        self.controller = AndroidController(port)

    def _pre_oracle(self):
        pass

    def _oracle(self) -> bool:
        pass

    def _body(self):
        pass

    def _cleanup(self):
        pass

    def observeEnd(self):
        pass

    def observeStart(self):
        pass

    def act(self, action: str, attribs: dict, *param):
        flag = True
        cnt = 3
        while flag and cnt > 0:
            try:
                event: Event = RawHierarchy(self.controller.device.dump_hierarchy()).buildEvent(action, attribs, *param)
                event.act(self.controller)
                flag = False
            except:
                traceback.print_exc()
                cnt -= 1
        if cnt == 0:
            raise Exception("Failed")


    def check(self, rules: Dict[str, str], attrib: str = None, param: str = None) -> bool:
        oracle: Oracle = Oracle(rules, attrib, param)
        return oracle.verify(self.controller)

    def acquireApkName(self) -> str:
        testName = self.__class__.__name__
        if not testName.endswith("Test"):
            raise Exception("Test class name must end with 'Test'")
        apk = re.findall('[A-Z][^A-Z]*', testName)[0].lower()
        if apk not in configs.apk_info:
            raise Exception("Test class name must start with a valid apk name")
        return apk

    def run(self, init = True):
        apk = self.acquireApkName()
        print(f"init: {init}")
        if init and not setup_app(apk):
            raise Exception("Setup Failed for "+apk)

        self.observeStart()

        self._body()
        self.observeEnd()

        self._pre_oracle()
        self.observeEnd()

        result = self._oracle()
        if result:
            self._cleanup()
            self.observeEnd()
        #uninstall_app(apk)
        return result

class Simulator:
    test: Test

    @staticmethod
    def getStage() -> str:
        print(traceback.format_stack())
        return traceback.format_stack()[-3].split('\n')[0].split(', in _')[1].strip()

    def act(self: Test, action: str, attribs: dict, *param: str):
        # do action here
        ui = self.controller.device.dump_hierarchy()
        flag = True
        cnt = 3
        while flag and cnt > 0:
            try:
                event: Event = RawHierarchy(self.controller.device.dump_hierarchy()).buildEvent(action, attribs, *param)
                event.act(self.controller)
                flag = False
            except:
                cnt -= 1
                time.sleep((3-cnt)*2)
        if cnt == 0:
            raise Exception("Failed")
        #traceback.print_stack()

        stage = Simulator.getStage()
        idx = len(self.events)
        print(f"SAVING {idx}-TH UI FOR {stage}")
        with open(self.savePath / f"{stage}{idx}.xml", "w", encoding="utf-8") as f:
            f.write(self.controller.device.dump_hierarchy())
        print(f"SAVING {idx}-TH SCREEN SHOT FOR {stage}")
        util.save_current_screen(self.savePath / f"{stage}{idx}.png")
        self.events.append(event)

        self.lastStage = stage
        if stage not in self.sizeCnt:
            self.sizeCnt[stage] = 0
        self.sizeCnt[stage] += 1

    def observeEnd(self: Test):
        # output events
        if self.lastStage is not None:
            print(f"DUMPING EVENT SEQ FOR {self.lastStage}")
            self.events.dump(self.savePath / f"{self.lastStage}.json")
            self.events.clear()
            self.lastStage = None

    def observeStart(self: Test):
        with open(self.savePath / "init.xml", "w", encoding="utf-8") as f:
            f.write(self.controller.device.dump_hierarchy())
        util.save_current_screen(self.savePath / "init.png")

    def saveMetadata(self):
        print("SAVING METADATA")
        with open(self.savePath / "index.json", "w", encoding="utf-8") as f:
            json.dump(self.test.sizeCnt, f)

    def __init__(self, testClass: Type[Test], port: str):
        self.test = testClass()
        self.savePath = Path('.') / "test_cases" / testClass.__name__
        self.test.savePath = self.savePath
        self.test.controller = AndroidController(port)
        if (self.savePath / "index.json").exists():
            print(str(self.savePath) + " already has metadata in it!")
            return
        if self.savePath.exists():
            shutil.rmtree(self.savePath)
        self.savePath.mkdir(parents=True, exist_ok=True)

    def check(self: Test, rules: Dict[str, str], attrib: str = None, param: str = None) -> bool:
        widget: Widget = self.last_hierarchy.buildWidget(rules)
        w = widget.dumpAsDict()
        with open(self.savePath / "oracle.json", "w", encoding="utf-8") as f:
            json.dump({"widget": w, "attrib": attrib, "param": param}, f)
        oracle: Oracle = Oracle(rules, attrib, param)
        return oracle.verify(self.controller)

    # do validate before siming
    def validate(self, init = True) -> bool:
        try:
            return self.test.run(init)
        except Exception as e:
            print(e)
            return False

    def sim(self, init=True):
        if (self.savePath / "index.json").exists():
            print(str(self.savePath) + " already has metadata in it!")
            return
        self.test.sizeCnt = {}
        self.test.lastStage = None

        self.test.observeStart = Simulator.observeStart.__get__(self.test, Test)
        self.test.act = Simulator.act.__get__(self.test, Test)
        self.test.observeEnd = Simulator.observeEnd.__get__(self.test, Test)
        self.test.run(init)
        self.saveMetadata()

    def sim_oracle(self):
        if (self.savePath / "oracle.json").exists():
            print(str(self.savePath) + " already has oracle in it!")
            return
        testCase = TestCase.loadFromDisk(self.savePath)
        self.test.last_hierarchy = testCase._hierarchies[-1]
        self.test.check = Simulator.check.__get__(self.test, Test)
        self.test._oracle()

"""
actual test classes
"""

class MerriamwebsterTest(Test):

    def tap_favorite(self):
        self.act("click", {RESOURCEID: "com.merriamwebster:id/titlebar_fav"})

class MerriamwebsterSearchForHelloTest(MerriamwebsterTest):
    """search for hello"""

    def _body(self):
        self.act("text", {RESOURCEID: "com.merriamwebster:id/search_src_text"}, 'hello')
        self.act("click", {TEXT: "hello", RESOURCEID: "android:id/text1"})

    def _oracle(self):
        # TODO: SOME PROBLEM HERE
        return self.check({TEXT: "hello", CLASS: "android.widget.TextView"})

class MerriamwebsterRecentWordTest(MerriamwebsterTest):
    """search for hello and check if it is in recent words"""
    def _body(self):
        self.act("text", {RESOURCEID: "com.merriamwebster:id/search_src_text"}, 'hello')
        self.act("click", {TEXT: "hello", RESOURCEID: "android:id/text1"})

    def _pre_oracle(self):
        self.act("click", {CONTENTDESC: "Open menu drawer"})
        self.act("click", {RESOURCEID: "com.merriamwebster:id/menu_recents"})

    def _oracle(self):
        return self.check({TEXT: "hello"})

"""
class MerriamwebsterPauseGameTest(MerriamwebsterTest):
    start a light game and pause it
    def _body(self):
        self.act("click", {CONTENTDESC: "Open menu drawer"})
        self.act("click", {RESOURCEID: "com.merriamwebster:id/menu_games"})
        self.act("click", {TEXT: "Light"})
        self.act("click", {RESOURCEID: "com.merriamwebster:id/game_play_instructions_play"})
        self.act("click", {RESOURCEID: "com.merriamwebster:id/game_play_pause"})

    def _oracle(self):
        return self.check({TEXT: "Quiz paused"}, None, None)
"""

class QuizletTest(Test):
    pass

class QuizletTurnOnNightModeTest(QuizletTest):
    """turn on night mode"""

    def _body(self):
        self.act('click', {RESOURCEID: 'com.quizlet.quizletandroid:id/bottom_nav_menu_account'})
        self.act('swipe', {RESOURCEID: 'com.quizlet.quizletandroid:id/user_settings_scroll_view'})
        self.act('click', {RESOURCEID: 'com.quizlet.quizletandroid:id/user_settings_nightmode_content_wrapper'})
        self.act('click', {RESOURCEID: 'com.quizlet.quizletandroid:id/user_settings_night_mode_switch'})

    def _pre_oracle(self):
        self.act('back', {CONTENTDESC: 'Navigate up'})

    def _oracle(self):
        # TODO: we need to check here also the color of the screen
        return self.check(
            {RESOURCEID: "com.quizlet.quizletandroid:id/user_settings_nightmode_text_indicator"}, 'text', "On")

    def _cleanup(self):
        self.act('click', {RESOURCEID: 'com.quizlet.quizletandroid:id/user_settings_nightmode_content_wrapper'})
        self.act('click', {RESOURCEID: 'com.quizlet.quizletandroid:id/user_settings_night_mode_switch'})

class QuizletAppVersionTest(QuizletTest):
    """check that the version of the app is 6.6.2"""

    def _body(self):
        self.act(CLICK, {RESOURCEID: 'com.quizlet.quizletandroid:id/bottom_nav_menu_account'})
        self.act(SWIPE, {RESOURCEID: 'com.quizlet.quizletandroid:id/user_settings_scroll_view'})
        self.act(SWIPE, {RESOURCEID: 'com.quizlet.quizletandroid:id/user_settings_scroll_view'})

    def _oracle(self):
        return self.check(
            {RESOURCEID: "com.quizlet.quizletandroid:id/user_settings_version"}, TEXT, "6.6.2 (2100170)")

class LinewebtoonTest(Test):

    def open_settings(self):
        self.act("click", {TEXT: "More"})
        self.act("click", {TEXT: "Settings"})

class LinewebtoonAppVersionTest(LinewebtoonTest):
    """check if app version is 2.4.3"""

    def _body(self):
        self.act("click", {TEXT: "More"})
        self.act("click", {TEXT: "Settings"})
        self.act("swipe", {CLASS: "android.widget.ListView"})
        self.act("swipe", {CLASS: "android.widget.ListView"})
        self.act("swipe", {CLASS: "android.widget.ListView"})
        self.act("swipe", {CLASS: "android.widget.ListView"})
        self.act("click", {TEXT: "App Version"})

    def _oracle(self):
        return self.check({RESOURCEID: "com.naver.linewebtoon:id/current_version"}, TEXT, "Current Version 2.4.3")

class LinewebtoonOpenSleepModeTest(LinewebtoonTest):
    """open sleep mode"""

    def _body(self):
        self.act("click", {TEXT: "More"})
        self.act("click", {TEXT: "Settings"})
        self.act("swipe", {CLASS: "android.widget.ListView"})
        self.act("swipe", {CLASS: "android.widget.ListView"})
        self.act("click", {TEXT: "Sleep Mode"})

    def _oracle(self):
        # TODO: we can do better here
        return self.check({RESOURCEID: "android:id/summary"}, None, None)

    def _cleanup(self):
        self.act("click", {TEXT: "Sleep Mode"})

class LinewebtoonSearchToonTest(LinewebtoonTest):
    """search for Lore Olympus by Rachel Smythe"""

    def _body(self):
        self.act("click", {RESOURCEID: "com.naver.linewebtoon:id/search"})
        self.act("text", {RESOURCEID: "com.naver.linewebtoon:id/search_edit_text"}, "Lore Olympus")

    def _oracle(self):
        # TODO: we can do better here
        return self.check({RESOURCEID: "com.naver.linewebtoon:id/search_result_title"}, TEXT, "Lore Olympus")

class LinewebtoonMostLikedOriginalTest(LinewebtoonTest):
    """check the most liked fantasy original is Lore Olympus"""

    def _body(self):
        self.act("click", {CONTENTDESC: "ORIGINALS"})
        self.act("click", {TEXT: "Close"})
        self.act("click", {RESOURCEID: "com.naver.linewebtoon:id/genre_tab"})
        self.act("click", {CONTENTDESC: "Fantasy"})
        self.act("click", {TEXT: "Sort by Popularity"})
        self.act("click", {TEXT: "Sort by Likes"})

    def _oracle(self):
        return self.check({TEXT: "Lore Olympus"})

class TripadvisorTest(Test):
    pass

class TripadvisorAddTripWithNameTest(TripadvisorTest):
    """add a trip with name foobar"""
    def _body(self):
        self.act("click", {TEXT: "My Trips"})
        self.act("click", {RESOURCEID: "com.tripadvisor.tripadvisor:id/action_create"})
        self.act("text", {RESOURCEID: "com.tripadvisor.tripadvisor:id/input_trip_name_edit_text"}, "foobar")
        self.act('click', {RESOURCEID: "com.tripadvisor.tripadvisor:id/action_done"})

    def _oracle(self):
        return self.check({BOUNDS: "[32,288][126,331]"}, TEXT, "foobar")

    def _cleanup(self):
        self.act("click", {BOUNDS: "[32,288][126,331]"})
        self.act("click", {CONTENTDESC: "More options"})
        self.act("click", {TEXT: "Delete trip"})
        self.act(CLICK, {TEXT: "Delete"})

class TripadvisorLanguageTest(TripadvisorTest):
    """change language to Chinese (China)"""
    def _body(self):
        self.act("click", {TEXT: "Me"})
        self.act(SWIPE, {RESOURCEID: "com.tripadvisor.tripadvisor:id/me_recycler_view"})
        self.act(CLICK, {TEXT: "Settings"})
        self.act(CLICK, {TEXT: "Language"})
        self.act(CLICK, {TEXT: "Chinese (China)"})
        self.act(CLICK, {RESOURCEID: "com.tripadvisor.tripadvisor:id/action_done"})
        time.sleep(5)

    def _oracle(self):
        return self.check({TEXT: "语言"})

class TripadvisorSearchTest(TripadvisorTest):
    """change trip target to London and search for Buckingham Palace"""

    def _body(self):
        self.act('click', {TEXT: 'Where to?'})
        self.act('text', {RESOURCEID: 'com.tripadvisor.tripadvisor:id/query_text'}, 'London')
        self.act(CLICK, {BOUNDS: "[32,357][736,400]"})
        self.act(CLICK, {RESOURCEID: "com.tripadvisor.tripadvisor:id/search_image"})
        self.act(TEXT, {RESOURCEID: "com.tripadvisor.tripadvisor:id/what_query_text"}, 'Buckingham Palace')

    def _oracle(self):
        return self.check({TEXT: "Buckingham Palace"})


"""
class SpotifyTest(Test):

    def delete_first_list():
        adb_tap_center('[64,1072][262,1184]') # tap your playlists
        adb_tap_center('[216,468][336,509]') # tap the list
        adb_tap_center('[640,64][720,144]') # tap the '...' sign
        adb_tap_center('[32,816][390,928]') # delete list
        adb_tap_center('[361,670][702,766]') # delete

class SpotifySearchSingerTest(SpotifyTest):
    "search for singer Lady Gaga"
    def _body(self):
        self.act(CLICK, {RESOURCEID: "com.spotify.music:id/search_tab"})
        self.act(CLICK, {TEXT: "Artist, song, or playlist"})
        self.act(TEXT, {RESOURCEID: "com.spotify.music:id/query"}, "Lady Gaga")
        self.act(CLICK, {BOUNDS: "[152,184][309,225]"})


    def _oracle(self):
        return self.check({RESOURCEID: "com.spotify.music:id/title"}, TEXT, "Lady Gaga")

class SpotifyCreateListWithGivenNameTest(SpotifyTest):
    "create a list with name foobar"
    def _body(self):
        self.act(CLICK, {RESOURCEID: "com.spotify.music:id/your_library_tab"})
        self.act(CLICK, {TEXT: "Create"})
        self.act(TEXT, {RESOURCEID: "com.spotify.music:id/edit_text"}, "foobar")

    def _pre_oracle(self):
        self.act(CLICK, {CONTENTDESC: "Back"})

    def _oracle(self) -> bool:
        return self.check({TEXT: "foobar"})

    def _cleanup(self):
        SpotifyTest.delete_first_list()
"""

class GoodrxTest(Test):
    pass

class GoodrxAppVersionTest(GoodrxTest):
    """check if app version is 5.3.6"""

    def _body(self):
        self.act(CLICK, {TEXT: "Settings"})
        self.act(SWIPE, {CLASS: "android.widget.ScrollView"})
        self.act(SWIPE, {CLASS: "android.widget.ScrollView"})

    def _oracle(self):
        return self.check({RESOURCEID: "com.goodrx:id/textview_version"}, TEXT, "v5.3.6")

class GoodrxAddPrescriptionTest(GoodrxTest):
    """add a presciption for aspirin"""
    def _body(self):
        self.act(CLICK, {TEXT: "My Rx"})
        self.act(CLICK, {RESOURCEID: "com.goodrx:id/floating_action_button"})
        self.act(TEXT, {TEXT: "Add a drug to My Rx", CLASS: "android.widget.EditText"}, "Aspirin")
        self.act(CLICK, {TEXT: "aspirin"})
        self.act(CLICK, {RESOURCEID: "com.goodrx:id/button_rxedit_add"})

    def _oracle(self):
        return self.check({RESOURCEID: "com.goodrx:id/textview_myrx_name"}, TEXT, "aspirin")

    def _cleanup(self):
        self.act(CLICK, {RESOURCEID: "com.goodrx:id/textview_myrx_name"})
        self.act(CLICK, {CONTENTDESC: "Edit Prescription"})
        self.act(CLICK, {TEXT: "Delete Prescription"})
        self.act(CLICK, {TEXT: "OK"})

class GoodrxSearchTreatmentTest(GoodrxTest):
    """search for insomnia and check that NSAIDs is a common treatment"""
    def _body(self):
        self.act(TEXT, {TEXT: "Search for a drug or condition"}, "insomnia")
        #self.act(CLICK, {TEXT: "My Rx"})
        self.act(CLICK, {TEXT: "Insomnia", RESOURCEID: "com.goodrx:id/textview"})

    def _oracle(self):
        return self.check({TEXT: "NSAIDs"})

class GoodrxIdentifyPillTest(GoodrxTest):
    """identify a green capsule pill and verify that it is Absorica LD"""
    def _body(self):
        self.act(CLICK, {TEXT: "Identify a Pill"})
        self.act(CLICK, {TEXT: "Get Started"})
        self.act(CLICK, {TEXT: "Any Color"})
        self.act(CLICK, {TEXT: "Green"})
        self.act(CLICK, {TEXT: "Any Shape"})
        self.act(CLICK, {TEXT: "Capsule"})

    def _oracle(self):
        return self.check({RESOURCEID: "com.goodrx:id/textview_identifier_result_title"}, TEXT, "Absorica LD")

class GoogletranslateTest(Test):
    pass

class GoogletranslateHelloTest(GoogletranslateTest):
    """translate 'hello' to spanish and verify that the result is 'hola'"""

    def _body(self):
        self.act(CLICK, {RESOURCEID: "com.google.android.apps.translate:id/touch_to_type_text",
                         TEXT: "Tap to enter text"})
        self.act(TEXT, {RESOURCEID: "com.google.android.apps.translate:id/edit_input",
                         TEXT: "Enter text (English)"}, "hello")
        self.act(CLICK, {TEXT: "hello", RESOURCEID: "android:id/text1"})

    def _oracle(self):
        return self.check({TEXT: "Hola"})

class GoogletranslateHelloToFrenchTest(GoogletranslateTest):
    """translate 'hello' to French and verify that the result is 'bonjour'"""

    def _body(self):
        self.act(CLICK, {CONTENTDESC: "Translated language: Spanish.",
                         RESOURCEID: "com.google.android.apps.translate:id/picker2"})
        self.act(CLICK, {RESOURCEID: "com.google.android.apps.translate:id/languages_search",
                         CONTENTDESC: "Search"})
        self.act(TEXT, {RESOURCEID: "com.google.android.apps.translate:id/search_src_text"}, "French")
        self.act(CLICK, {TEXT: "French", RESOURCEID: "android:id/text1"})
        self.act(CLICK, {RESOURCEID: "com.google.android.apps.translate:id/touch_to_type_text",
                         TEXT: "Tap to enter text"})
        self.act(TEXT, {RESOURCEID: "com.google.android.apps.translate:id/edit_input",
                        TEXT: "Enter text (English)"}, "hello")
        self.act(CLICK, {TEXT: "hello", RESOURCEID: "android:id/text1"})

    def _oracle(self):
        return self.check({TEXT: "Bonjour"})

class GoogletranslateRecentLanguagesTest(GoogletranslateTest):
    """select Albanian as the translation language and verify that it is in the recent languages"""

    def _body(self):
        self.act(CLICK, {CONTENTDESC: "Translated language: Spanish.",
                         RESOURCEID: "com.google.android.apps.translate:id/picker2"})
        self.act(CLICK, {TEXT: "Albanian", RESOURCEID: "android:id/text1"})
        self.act(CLICK, {CONTENTDESC: "Translated language: Albanian.",
                         RESOURCEID: "com.google.android.apps.translate:id/picker2"})

    def _oracle(self):
        return self.check({TEXT: "Albanian"})

# test for googlechrome starts here
class GooglechromeTest(Test):

    def go_to(prompt):
        adb_tap_center('[40,58][516,148]')
        adb_input(f"text {prompt}")
        adb_input("keyevent KEYCODE_ENTER", 5) # press enter

    @staticmethod
    def get_url():
        tree = get_current_ui()
        full_url = tree.findall(".//node[@resource-id='com.android.chrome:id/url_bar']")[0].attrib['text']
        seps = full_url.split('/')
        if len(seps) > 1:
            return seps[2]
        return seps[0]


class GooglechromeOpenIncognitoTest(GooglechromeTest):
    """open an incognito tab"""
    def _body(self):
        self.act(CLICK, {CONTENTDESC: "More options"})
        self.act(CLICK, {CONTENTDESC: "New incognito tab", TEXT: "New incognito tab"})

    def _oracle(self):
        return self.check({RESOURCEID: "com.android.chrome:id/ntp_incognito_header"},
                          TEXT, "You’ve gone incognito.")

class GooglechromeBookmarkTest(GooglechromeTest):
    """bookmark the home page and check bookmark for the page"""
    def _body(self):
        self.act(CLICK, {CONTENTDESC: "More options"})
        self.act(CLICK, {CONTENTDESC: "Bookmark this page"})

    def _pre_oracle(self):
        self.act(CLICK, {CONTENTDESC: "More options"})
        self.act(CLICK, {CONTENTDESC: "Bookmarks", TEXT: "Bookmarks"})

    def _oracle(self):
        return self.check({RESOURCEID: "com.android.chrome:id/title", TEXT: "New tab"})

class GooglechromeAppVersionTest(GooglechromeTest):
    """verify that the app version is 65.0.3325.109"""

    def _body(self):
        self.act(CLICK, {CONTENTDESC: "More options"})
        self.act(CLICK, {CONTENTDESC: "Settings", TEXT: "Settings"})
        self.act(SWIPE, {RESOURCEID: "android:id/list"})
        self.act(CLICK, {TEXT: "About Chrome"})

    def _oracle(self):
        return self.check({TEXT: "Chrome 65.0.3325.109"})


class AccuweatherTest(Test):
    pass


class AccuweatherLondonTest(AccuweatherTest):
    """search for the weather in london"""

    def _body(self):
        self.act(CLICK, {RESOURCEID: "com.accuweather.android:id/location_button"})
        self.act(TEXT, {RESOURCEID: "com.accuweather.android:id/location_search_box"}, "London")
        self.act(CLICK, {TEXT: "London, London, GB"})

    def _oracle(self):
        return self.check({RESOURCEID: "com.accuweather.android:id/location_button"}, TEXT, "London, GB")

class AccuweatherFavouriteLocationTest(AccuweatherTest):
    """set London as favourite without enabling notification"""
    def _body(self):
        self.act(CLICK, {RESOURCEID: "com.accuweather.android:id/location_button"})
        self.act(TEXT, {RESOURCEID: "com.accuweather.android:id/location_search_box"}, "London")
        self.act(CLICK, {RESOURCEID: "com.accuweather.android:id/action_icon_image_add_favorite"})
        self.act(CLICK, {TEXT: "No Thanks"})

    def _pre_oracle(self):
        self.act(CLICK, {RESOURCEID: "com.accuweather.android:id/location_search_cancel"})

    def _oracle(self) -> bool:
        return self.check({RESOURCEID: "com.accuweather.android:id/city",
                           TEXT: "London"})

class AccuweatherDefaultLocationTest(AccuweatherTest):
    """set London for favourites and set default location to London"""

    def _body(self):
        self.act(CLICK, {RESOURCEID: "com.accuweather.android:id/location_button"})
        self.act(TEXT, {RESOURCEID: "com.accuweather.android:id/location_search_box"}, "London")
        self.act(CLICK, {RESOURCEID: "com.accuweather.android:id/action_icon_image_add_favorite"})
        self.act(CLICK, {TEXT: "No Thanks"})
        self.act(BACK, {RESOURCEID: "com.accuweather.android:id/location_search_cancel"})

        self.act(CLICK, {CONTENTDESC: "Open navigation drawer"})
        self.act(CLICK, {TEXT: "Settings"})
        self.act(SWIPE, {CLASS: "android.widget.ScrollView"})
        self.act(CLICK, {RESOURCEID: "com.accuweather.android:id/default_location_cta"})
        self.act(CLICK, {RESOURCEID: "com.accuweather.android:id/city", TEXT: "London"})

    def _pre_oracle(self):
        self.act(BACK, {CONTENTDESC: "Navigate up"})
        self.act(BACK, {CONTENTDESC: "Navigate up"})
        self.act(CLICK, {RESOURCEID: "com.accuweather.android:id/location_button"})

    def _oracle(self):
        return self.check({TEXT: "London"})

class AccuweatherDisplayModeTest(AccuweatherTest):
    """set Display Mode to Dark"""

    def _body(self):
        self.act(CLICK, {CONTENTDESC: "Open navigation drawer"})
        self.act(CLICK, {TEXT: "Settings"})
        self.act(CLICK, {TEXT: "Dark"})

    def _pre_oracle(self):
        pass

    def _oracle(self):
        # TODO: oracle here?
        pass


class Autoscout24Test(Test):
    pass


class Autoscout24SearchTest(Autoscout24Test):
    """search for car 9ff model GT9"""

    def _body(self):
        self.act(CLICK, {RESOURCEID: "com.autoscout24:id/home_header_search_button", TEXT: "Start search"})
        self.act(CLICK, {TEXT: "Make", RESOURCEID: "com.autoscout24:id/fragment_search_parameter_item_heading"})
        self.act(CLICK, {TEXT: "9ff", RESOURCEID: "com.autoscout24:id/list_item_one_textline_label"})
        self.act(CLICK, {TEXT: "Model", RESOURCEID: "com.autoscout24:id/fragment_search_parameter_item_heading"})
        self.act(CLICK, {TEXT: "GT9"})
        self.act(CLICK, {TEXT: "OK", RESOURCEID: "com.autoscout24:id/standard_dialog_buttons_ok"})
        self.act(CLICK, {RESOURCEID: "com.autoscout24:id/fragment_search_button_results"})

    def _oracle(self):
        return self.check({RESOURCEID: "com.autoscout24:id/result_list_item_title"}, TEXT, "9ff GT9")

class Autoscout24FavouriteTest(Autoscout24Test):
    """search for car AC model Cobra and add it to my favourites"""

    def _body(self):
        self.act(CLICK, {RESOURCEID: "com.autoscout24:id/home_header_search_button", TEXT: "Start search"})
        self.act(CLICK, {TEXT: "Make", RESOURCEID: "com.autoscout24:id/fragment_search_parameter_item_heading"})
        self.act(CLICK, {TEXT: "AC", RESOURCEID: "com.autoscout24:id/list_item_one_textline_label"})
        self.act(CLICK, {TEXT: "Model", RESOURCEID: "com.autoscout24:id/fragment_search_parameter_item_heading"})
        self.act(CLICK, {TEXT: "Cobra"})
        self.act(CLICK, {TEXT: "OK", RESOURCEID: "com.autoscout24:id/standard_dialog_buttons_ok"})
        self.act(CLICK, {RESOURCEID: "com.autoscout24:id/fragment_search_button_results"})
        self.act(CLICK, {RESOURCEID: "com.autoscout24:id/result_list_favourite_icon"})

    def _pre_oracle(self):
        self.act(CLICK, {TEXT: "Favourites", RESOURCEID: "com.autoscout24:id/bottom_bar_item_text"})
        self.act(CLICK, {TEXT: "No, thanks"})

    def _oracle(self):
        return self.check({RESOURCEID: "com.autoscout24:id/car_title"}, TEXT, "AC Cobra")

class Autoscout24DarkThemeTest(Autoscout24Test):
    """set dark theme"""

    def _body(self):
        self.act(CLICK, {CONTENTDESC: "Navigate up"})
        self.act(CLICK, {TEXT: "Settings", RESOURCEID: "com.autoscout24:id/drawer_item_textview"})
        self.act(CLICK, {TEXT: "Appearance", RESOURCEID: "com.autoscout24:id/theme_settings_title"})
        self.act(CLICK, {TEXT: "Dark theme", RESOURCEID: "com.autoscout24:id/dark_theme_button"})

    def _pre_oracle(self):
        self.act(CLICK, {TEXT: "Appearance", RESOURCEID: "com.autoscout24:id/theme_settings_title"})

    def _oracle(self):
        return self.check({TEXT: "Dark theme", RESOURCEID: "com.autoscout24:id/dark_theme_button"}, "checked", "true")

class MarvelcomicsTest(Test):
    pass

class MarvelcomicsLocationTest(MarvelcomicsTest):
    """change download location to SD card"""

    def _body(self):
        self.act(CLICK, {CONTENTDESC: "Open navigation drawer"})
        self.act(CLICK, {TEXT: "SETTINGS"})
        self.act(SWIPE, {CLASS: "android.widget.ListView"})
        self.act(SWIPE, {CLASS: "android.widget.ListView"})
        self.act(CLICK, {TEXT: "Download location"})
        self.act(CLICK, {TEXT: "SD card"})
        self.act(CLICK, {TEXT: "Confirm"})

    def _oracle(self):
        return self.check({TEXT: "SD card", RESOURCEID: "android:id/summary"})


class MarvelcomicsVersionTest(MarvelcomicsTest):
    """check if app version is 3.10.20.310432"""

    def _body(self):
        self.act(CLICK, {CONTENTDESC: "Open navigation drawer"})
        self.act(SWIPE, {RESOURCEID: "com.marvel.comics:id/NavigationActivity_navigationList"})
        self.act(CLICK, {TEXT: "ABOUT"})

    def _oracle(self):
        return self.check({RESOURCEID: "com.marvel.comics:id/about_version_copyright"}, TEXT, "Version 3.10.3.310306")


class BbcnewsTest(Test):
    pass

class BbcnewsTabTest(BbcnewsTest):
    '''Go to the popular tab and click on the second most read article'''
    def _body(self):
        self.act(CLICK, {CONTENTDESC: "Popular"})
        self.act(CLICK, {BOUNDS: "[16,524][752,706]"})
        pass

class BbcnewsTechnologyTest(BbcnewsTest):
    '''view technology headlines'''
    def _body(self):
        self.act(CLICK, {RESOURCEID: "bbc.mobile.news.ww:id/action_search"})
        self.act(TEXT, {RESOURCEID: "bbc.mobile.news.ww:id/search"}, "Technology")
        self.act(CLICK, {RESOURCEID: "bbc.mobile.news.ww:id/chip_item", TEXT: "Technology"})
        pass

class AccuweatherNotificationTest(AccuweatherTest):
    '''Go to settings and turn off the use of current location'''
    def _body(self):
        self.act(CLICK, {CONTENTDESC: "Open navigation drawer"})
        self.act(CLICK, {RESOURCEID: "com.accuweather.android:id/settings_fragment"})
        self.act(CLICK, {TEXT: "Manage Notifications"})
        self.act(CLICK, {RESOURCEID: "com.accuweather.android:id/persistent_notification_switch"})
        pass

class AccuweatherTemperatureTest(AccuweatherTest):
    '''Open settings and change temperature unit to C'''
    def _body(self):
        self.act(CLICK, {CONTENTDESC: "Open navigation drawer"})
        self.act(CLICK, {RESOURCEID: "com.accuweather.android:id/settings_fragment"})
        self.act(CLICK, {BOUNDS: "[270,278][498,390]"})
        pass

class DiaryTest(Test):
    pass

class DiaryCreateTest(DiaryTest):
    '''Create a new entry'''
    def _body(self):
        self.act(CLICK, {CONTENTDESC: "Write note"})
        self.act(CLICK, {CONTENTDESC: "Save"})
        self.act(CLICK, {TEXT: "Yes"})
        pass

class DiaryExportTest(DiaryTest):
    '''export diary entries'''
    def _body(self):
        self.act(CLICK, {CLASS: "android.widget.ImageButton"})
        self.act(CLICK, {BOUNDS: "[0,672][560,768]"})
        self.act(CLICK, {TEXT: "Export now"})
        pass

class DiaryReminderTest(DiaryTest):
    '''set a daily reminder to write my diary'''
    def _body(self):
        self.act(CLICK, {CLASS: "android.widget.ImageButton"})
        self.act(CLICK, {BOUNDS: "[0,576][560,672]"})
        self.act(CLICK, {CONTENTDESC: "Save"})
        pass

class ChanelweatherTest(Test):
    pass

class ChanelweatherLocationTest(ChanelweatherTest):
    '''Go to settings and turn off the use of current location'''
    def _body(self):
        self.act(CLICK, {RESOURCEID: "com.chanel.weather.forecast.accu:id/btn_menu"})
        self.act(CLICK, {RESOURCEID: "com.chanel.weather.forecast.accu:id/llLocation", CLASS: "android.widget.LinearLayout", BOUNDS: "[0,247][614,354]"})
        self.act(CLICK, {RESOURCEID: "com.chanel.weather.forecast.accu:id/llyt_current_location"})


class ChanelweatherNotificationTest(ChanelweatherTest):
    '''Open notification settings and turn off notifications'''
    def _body(self):
        self.act(CLICK, {RESOURCEID: "com.chanel.weather.forecast.accu:id/btn_menu"})
        self.act(CLICK, {RESOURCEID: "com.chanel.weather.forecast.accu:id/ll_notifi"})
        self.act(CLICK, {RESOURCEID: "com.chanel.weather.forecast.accu:id/llyt_daily_noti"})
        self.act(CLICK, {RESOURCEID: "com.chanel.weather.forecast.accu:id/toggle_notiff_show"})

class DevweatherTest(Test):
    pass

class DevweatherLocationTest(DevweatherTest):
    '''Go to settings and turn off the use of current location'''
    def _body(self):
        self.act(CLICK, {CONTENTDESC: "Navigate up"})
        self.act(CLICK, {RESOURCEID: "com.devexpert.weather:id/menu_settings"})
        self.act(CLICK, {BOUNDS: "[30,259][738,401]"})


class DevweatherShowTest(DevweatherTest):
    '''Show me the temperature forecast over New Orleans Louisiana'''
    def _body(self):
        self.act(CLICK, {CONTENTDESC: "More options"})
        self.act(CLICK, {BOUNDS: "[368,56][760,152]"})
        self.act(TEXT, {RESOURCEID: "com.devexpert.weather:id/inputCountry"}, "New Orleans Louisiana")
        self.act(CLICK, {TEXT: "Search Now"})

class DominosTest(Test):
    pass

class DominosSettingTest(DominosTest):
    '''go to settings and turn off special offers and deals'''
    def _body(self):
        self.act(CLICK, {CONTENTDESC: "Expand Menu"})
        self.act(CLICK, {BOUNDS: "[0,720][560,780]"})
        self.act(CLICK, {RESOURCEID: "com.dominospizza:id/notification_center_marketing_switch"})

class GooglenewsTest(Test):
    pass

class GooglenewsProfileTest(GooglenewsTest):
    '''go to my profile'''
    def _body(self):
        self.act(CLICK, {RESOURCEID: "com.google.android.apps.magazines:id/selected_account_disc"})
        pass

class GooglenewsTechnologyTest(GooglenewsTest):
    '''view technology headlines'''
    def _body(self):
        self.act(CLICK, {RESOURCEID: "com.google.android.apps.magazines:id/tab_headlines"})
        self.act(CLICK, {CONTENTDESC: "Technology"})
        pass

# class CalendarTest(Test):
#     pass

# class CalendarNotificationTest(CalendarTest):
#     '''go to notification'''
#     def _body(self):
#         self.act(CLICK, {CONTENTDESC: "Show Calendar List and Settings drawer"})
#         self.act(SWIPE, {RESOURCEID: "com.google.android.calendar:id/drawer_list"})
#         self.act(CLICK, {BOUNDS: "[148,1012][736,1076]"})
#         self.act(CLICK, {BOUNDS: "[0,160][768,246]"})
#         pass

# class GmailTest(Test):
#     pass

# class GmailDraftsTest(GmailTest):
#     '''view drafts'''
#     def _body(self):
#         self.act(CLICK, {CONTENTDESC: "Navigate up"})
#         self.act(CLICK, {BOUNDS: "[0,1126][608,1184]"})

class SoundhoundTest(Test):
    pass

class SoundhoundHistoryTest(SoundhoundTest):
    '''Open settings and clear search history'''
    def _body(self):
        self.act(CLICK, {RESOURCEID: "com.melodis.midomiMusicIdentifier.freemium:id/nav_history"})
        self.act(CLICK, {RESOURCEID: "com.melodis.midomiMusicIdentifier.freemium:id/settings_button"})
        self.act(SWIPE, {RESOURCEID: "com.melodis.midomiMusicIdentifier.freemium:id/recycler_view"})
        self.act(SWIPE, {RESOURCEID: "com.melodis.midomiMusicIdentifier.freemium:id/recycler_view"})
        self.act(CLICK, {TEXT: "Clear My History"})
        # todo: This widget is not clickable... but we need swipe... so I cant locate by bounds
        self.act(CLICK, {TEXT: "Delete"})
        pass

class SoundhoundMusicTest(SoundhoundTest):
    '''Play Christmas Music'''
    def _body(self):
        self.act(TEXT, {BOUNDS: "[32,80][736,176]"}, "Christmas Music")
        self.act(CLICK, {TEXT: "christmas music"})
        self.act(CLICK, {TEXT: "Christmas Music"})
        # not good
        self.act(CLICK, {TEXT: "Done"})
        pass

class PhotomathTest(Test):
    pass

class PhotomathLanguageTest(PhotomathTest):
    '''Change language to Spanish'''
    def _body(self):
        self.act(CLICK, {RESOURCEID: "com.microblink.photomath:id/menu_icon"})
        self.act(CLICK, {RESOURCEID: "com.microblink.photomath:id/menu_item_language"})
        self.act(SWIPE, {RESOURCEID: "com.microblink.photomath:id/language_list"})
        self.act(CLICK, {TEXT: "Spanish"})
        # not good
        self.act(CLICK, {TEXT: "Done"})
        pass

class PhotomathCalculatorTest(PhotomathTest):
    '''Open the advanced calculator'''
    def _body(self):
        self.act(CLICK, {RESOURCEID: "com.microblink.photomath:id/editor_icon"})
        pass

class TransitTest(Test):
    pass

class TransitSettingTest(TransitTest):
    '''go to settings'''
    def _body(self):
        self.act(CLICK, {BOUNDS: "[0,1048][153,1184]"})
        pass

class TedTest(Test):
    pass

class TedSearchTest(TedTest):
    '''click on \"Inside the mind of a master procrastinator\" Ted Talk and scroll down to read more information about the talk and speaker'''
    def _body(self):
        self.act(CLICK, {BOUNDS: "[154,1086][307,1184]"})
        self.act(TEXT, {TEXT: "Search"}, "Inside the mind of a master procrastinator")
        self.act(CLICK, {CONTENTDESC: "Search"})
        self.act(CLICK, {TEXT: "Tim Urban: Inside the mind of a master procrastinator"})
        self.act(SWIPE, {CLASS: "android.widget.ScrollView"})
        # not good
        pass

class TedTrendingTest(TedTest):
    '''take me to the trending section'''
    def _body(self):
        self.act(SWIPE, {CONTENTDESC: "Home Screen"})
        pass

class SheinTest(Test):
    pass

class SheinCategoryTest(SheinTest):
    '''shop by category'''
    def _body(self):
        self.act(CLICK, {CONTENTDESC: "Category"})
        pass

class SheinNewTest(SheinTest):
    '''view fresh & new clothes'''
    def _body(self):
        self.act(CLICK, {CONTENTDESC: "New"})
        pass

class SheinBagTest(SheinTest):
    '''view my shopping bag'''
    def _body(self):
        self.act(CLICK, {CONTENTDESC: "Cart"})
        pass

class CastboxTest(Test):
    pass

# class CastboxProfileTest(CastboxTest):
#     '''go to my profile'''
#     def _body(self):
#         self.act(CLICK, {CONTENTDESC: "Profiles and Settings"})
#         self.act(CLICK, {RESOURCEID: "fm.castbox.audiobook.radio.podcast:id/account_view"})
#         pass

class CastboxTechnologyTest(CastboxTest):
    '''view technology headlines'''
    def _body(self):
        self.act(CLICK, {CONTENTDESC: "Categories"})
        self.act(SWIPE, {RESOURCEID: "fm.castbox.audiobook.radio.podcast:id/recyclerView"})
        self.act(CLICK, {CONTENTDESC: "Technology"})
        pass

class NasaTest(Test):
    pass

class NasaImageTest(NasaTest):
    '''click on images and view first flight of saturn IB'''
    def _body(self):
        self.act(CLICK, {BOUNDS: "[5,661][379,981]"})
        self.act(CLICK, {CONTENTDESC: "Search"})
        self.act(TEXT, {CLASS: "android.widget.EditText"}, "first flight of saturn IB")
        self.act(CLICK, {CONTENTDESC: "Search"})
        self.act(SWIPE, {RESOURCEID: "gov.nasa:id/recycler_view"})
        self.act(SWIPE, {RESOURCEID: "gov.nasa:id/recycler_view"})
        pass

class NasaMissionTest(NasaTest):
    '''go to missions and click on apollo'''
    def _body(self):
        self.act(CLICK, {BOUNDS: "[389,1150][763,1184]"})
        self.act(CLICK, {TEXT: "All"})
        self.act(CLICK, {BOUNDS: "[2,643][382,963]"})
        pass

class NasaDarkmodeTest(NasaTest):
    '''Go to settings and use Dark Mode Theme'''
    def _body(self):
        self.act(CLICK, {CONTENTDESC: "Settings"})
        self.act(CLICK, {BOUNDS: "[0,252][768,359]"})
        pass

    
class AudibleTest(Test):
    pass

class AudibleListenTest(AudibleTest):
    '''listen to the sample of the audiobook "Modern Software Engineering".'''
    def _body(self):
        self.act(CLICK, {CONTENTDESC: "Search"})
        self.act(TEXT, {RESOURCEID: "com.audible.application:id/search_src_text"}, "Modern Software Engineering")
        self.act(CLICK, {RESOURCEID: "com.audible.application:id/title", TEXT: "Modern Software Engineering"})
        self.act(CLICK, {CONTENTDESC: "Play sample"})

class AudibleTimeTest(AudibleTest):
    '''check my total time spent listening.'''
    def _body(self):
        self.act(CLICK, {CONTENTDESC: "Profile"})
        self.act(SWIPE, {CLASS: "android.view.View"})
        self.act(CLICK, {CONTENTDESC: "Listening Time"})
        self.act(CLICK, {CONTENTDESC: "Total"})

class EspnTest(Test): 
    pass

class EspnPlayerTest(EspnTest):
    '''Show the player stats of Kobe.'''
    def _body(self):
        self.act(CLICK, {RESOURCEID: "button.search"})
        self.act(TEXT, {RESOURCEID: "com.espn.score_center:id/search_src_text"}, "Kobe")
        time.sleep(5)
        self.act(CLICK, {TEXT: "Kobe Bryant"})
        time.sleep(5)
        pass

class EspnStandingTest(EspnTest):
    '''Show the standings of NBA.'''
    def _body(self):
        self.act(CLICK, {RESOURCEID: "nav.More"})
        self.act(SWIPE, {RESOURCEID: "com.espn.score_center:id/sports_list"})
        self.act(CLICK, {TEXT: "NBA"})
        self.act(CLICK, {CONTENTDESC: "Standings"})
        time.sleep(5)
        pass

# class OnxTest(Test):
#     pass

# class OnxRouteTest(OnxTest):
#     "Route to Statue of Liberty."
#     def _body(self):
#         self.act(CLICK, {RESOURCEID: "onxmaps.offroad:id/toolbar_search"})
#         self.act(TEXT, {CLASS: "android.widget.EditText"}, "Statue of Liberty")


#         pass

# class OnxWeatherTest(OnxTest):
#     "show the weather of Washington, USA."
#     def _body(self):
#         time.sleep(5)
#         pass

class EtsyTest(Test):
    pass

class EtsySearchTest(EtsyTest):
    '''search for toy and add it to favorites'''
    def _body(self):
        self.act(TEXT, {RESOURCEID: "com.etsy.android:id/search_src_text"}, "toy")
        self.act(CLICK, {TEXT: "toys"})
        self.act(CLICK, {RESOURCEID: "com.etsy.android:id/favorite_button"})
        self.act(CLICK, {TEXT: "Done"})

class EtsyGiftTest(EtsyTest):
    '''give me some gift ideas for wife's birthday'''
    def _body(self):
        self.act(CLICK, {RESOURCEID: "com.etsy.android:id/menu_bottom_nav_gift_mode"})
        self.act(CLICK, {TEXT: "Wife"})
        self.act(CLICK, {TEXT: "Find the perfect gift"})
        self.act(CLICK, {TEXT: "Birthday"})
        self.act(CLICK, {TEXT: "Show gift ideas"})

class RedditTest(Test):
    pass

class RedditDarkModeTest(RedditTest):
    '''turn off auto dark mode and turn on dark mode'''
    def _body(self):
        self.act(CLICK, {CONTENTDESC: 'Major_Security_359 account'})
        self.act(CLICK, {RESOURCEID: 'com.reddit.frontpage:id/drawer_nav_settings'})
        self.act(SWIPE, {CLASS: 'androidx.recyclerview.widget.RecyclerView'})
        self.act(CLICK, {TEXT: 'Auto Dark Mode'})
        self.act(CLICK, {CONTENTDESC: 'Off'})
        self.act(CLICK, {TEXT: 'Dark mode'})

class RedditSubRedditTest(RedditTest):
    "enter Taylor Swift subreddit though my communities"
    def _body(self):
        self.act(CLICK, {BOUNDS: '[8,64][84,144]'})
        self.act(CLICK, {TEXT: 'r/TaylorSwift'})

class RedditPremiumTest(RedditTest):
    "check the price of reddit premium"
    def _body(self):
        self.act(CLICK, {CONTENTDESC: 'Major_Security_359 account'})
        self.act(SWIPE, {RESOURCEID: "com.reddit.frontpage:id/drawer_nav_items_scroll_view"})
        self.act(SWIPE, {RESOURCEID: "com.reddit.frontpage:id/drawer_nav_items_scroll_view"})
        self.act(SWIPE, {RESOURCEID: "com.reddit.frontpage:id/drawer_nav_items_scroll_view"})
        self.act(SWIPE, {RESOURCEID: "com.reddit.frontpage:id/drawer_nav_items_scroll_view"})
        self.act(CLICK, {CONTENTDESC: 'Reddit Premium, Ads-free browsing'})

class AgodaTest(Test):
    pass

class AgodaLanguageTest(AgodaTest):
    "change the language of the app to French"
    def _body(self):
        self.act(CLICK, {BOUNDS: '[614,1074][768,1184]'})
        self.act(SWIPE, {RESOURCEID: "com.agoda.mobile.consumer:id/menu_items_list"})
        self.act(SWIPE, {RESOURCEID: "com.agoda.mobile.consumer:id/menu_items_list"})
        self.act(CLICK, {RESOURCEID: 'com.agoda.mobile.consumer:id/menu_item_Language'})
        self.act(CLICK, {TEXT: 'Français'})

class AgodaPreviousReservationTest(AgodaTest):
    "check all previous reservations"
    def _body(self):
        self.act(CLICK, {BOUNDS: '[153,1074][306,1184]'})
        self.act(CLICK, {TEXT: 'All bookings'})

class AgodaFindHotelTest(AgodaTest):
    "find a room in London"
    def _body(self):
        self.act(CLICK, {BOUNDS: '[32,252][734,452]'})
        self.act(CLICK, {BOUNDS: '[64,334][704,430]'})
        self.act(TEXT, {RESOURCEID: 'com.agoda.mobile.consumer:id/textbox_textsearch_searchbox'}, 'London')
        self.act(CLICK, {RESOURCEID: 'com.agoda.mobile.consumer:id/place_name', TEXT: 'London'})
        self.act(CLICK, {BOUNDS: '[176,706][704,802]'})

def getTestList():
    clsmembers = inspect.getmembers(sys.modules[__name__], inspect.isclass)
    test_list = [
        {
            "test": cls[1],
            "apk": re.findall('[A-Z][^A-Z]*',cls[1].__base__.__name__)[0],
            "function": cls[1].__doc__.strip()
        }
        for cls in clsmembers if sum([ch.isupper() for ch in cls[0]]) > 2]
    return test_list

def getAdditionalTestList():
    test_list = getTestList()
    return [t for t in test_list if t["apk"]  in ["Reddit", "Agoda","Etsy","Espn","Audible"]]

if __name__ == "__main__":
    print(len(getAdditionalTestList()))
    exit(1)
    from colorama import Fore, Style
    port = "emulator-5554"
    o = open("truth_output.log", "w")
    tt = getTestList()[0:]
    for test in tt:
        name = test["test"].__name__
        if "audible" not in name.lower():
            continue
        if "yelp" in name.lower():
            continue
        try:
            simulator = Simulator(test["test"], port)
            simulator.sim()
        except Exception as e:
            o.write(name + "generation failed")
            o.write(traceback.format_exc() + "\n")
            print(Fore.RED + "Validation failed for", name)
            print(traceback.format_exc())
            print(Style.RESET_ALL)
    o.close()
    exit(0)
