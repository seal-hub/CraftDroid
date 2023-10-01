import time
from copy import deepcopy
import sys
import traceback
import os
from statistics import mean
import pickle
from collections import defaultdict
import math
from datetime import datetime

# local import
from Util import Util
from StrUtil import StrUtil
from Configuration import Configuration
from Runner import Runner
from WidgetUtil import WidgetUtil
# from misc import teardown_mail
from CallGraphParser import CallGraphParser
from ResourceParser import ResourceParser
from const import SA_INFO_FOLDER, SNAPSHOT_FOLDER


class Explorer:
    def __init__(self, config_id, appium_port='4723', udid=None):
        self.config = Configuration(config_id)
        self.runner = Runner(self.config.pkg_to, self.config.act_to, self.config.no_reset, appium_port, udid)
        self.src_events = Util.load_events(self.config.id, 'base_from')
        self.tid = self.config.id
        self.current_src_index = 0
        self.tgt_events = []
        self.f_target = 0
        self.prev_tgt_events = []
        self.f_prev_target = -1
        # self.is_rerun_required = True
        self.rp = ResourceParser(os.path.join(SA_INFO_FOLDER, self.config.id.split('-')[1]))
        self.widget_db = self.generate_widget_db()
        self.cgp = CallGraphParser(os.path.join(SA_INFO_FOLDER, self.config.id.split('-')[1]))
        self.invalid_events = defaultdict(list)
        self.nearest_button_to_text = None
        self.idx_src_to_tgt = {}
        self.skipped_match = defaultdict(list)
        self.consider_naf_only_widget = False

    def generate_widget_db(self):
        db = {}
        for w in self.rp.get_widgets():
            if w['activity']:
                # the signature here has no 'clickable' and 'password', bcuz it's from static info
                w_signature = WidgetUtil.get_widget_signature(w)
                db[w_signature] = w
        return db

    def mutate_src_action(self, mutant):
        # e.g., mutant = {'long_press': 'swipe_right', 'swipe_right': 'long_press'}
        for e in self.src_events:
            if e['action'][0] in mutant:
                e['action'][0] = mutant[e['action'][0]]

    def run(self):
        # todo: or exceed a time limit
        while self.f_target - self.f_prev_target > 0.001:  # still found a better solution
            print('--\nStart a new round to find a better tgt event sequence')
            print('Timestamp:', datetime.now())
            self.f_prev_target = self.f_target
            self.prev_tgt_events = self.tgt_events
            self.tgt_events = []
            self.current_src_index = 0

            if self.config.id[-3:] == 'b42':
                Util.delete_emails()

            # self.tgt_events = [
            #     {'class': 'EMPTY_EVENT', 'score': 0, 'event_type': 'oracle'},
            #     {'class': 'EMPTY_EVENT', 'score': 0, 'event_type': 'gui'}
            # ]
            # self.current_src_index = 2
            self.invalid_events = defaultdict(list)
            self.skipped_match = defaultdict(list)
            self.idx_src_to_tgt = {}
            is_explored = False
            while self.current_src_index < len(self.src_events):
                src_event = self.src_events[self.current_src_index]
                print(f'Source Event:\n{src_event}')

                if self.current_src_index == len(self.src_events) - 1 and src_event['event_type'] == "oracle":
                    self.consider_naf_only_widget = True  # e.g., a32-a33-b31
                else:
                    self.consider_naf_only_widget = False  # e.g., a35-a33-b31

                tgt_event = None
                # Just replicate previous src_event if that is an oracle and current one is the action for it
                if self.current_src_index > 0:
                    prev_src_event = self.src_events[self.current_src_index - 1]
                    if prev_src_event['event_type'] == 'oracle' and src_event['event_type'] == 'gui' \
                            and WidgetUtil.is_equal(prev_src_event, src_event) \
                            and self.tgt_events[-1]['class'] != 'EMPTY_EVENT':
                        tgt_event = deepcopy(self.tgt_events[-1])
                        if 'stepping_events' in tgt_event:
                            tgt_event['stepping_events'] = []
                        tgt_event['event_type'] = 'gui'
                        tgt_event['action'] = deepcopy(src_event['action'])
                        if self.check_skipped(tgt_event):  # don't copy previous src_event if it should be skipped
                            tgt_event = None
                        # todo: remember if the tgt_action is propagated the previous oracle;
                        #       if yes and skipped/rematched, also change the previous oracle

                if src_event['event_type'] == 'SYS_EVENT':
                    # e.g., {"class": "SYS_EVENT","action": ["KEY_BACK"], "event_type":  "SYS_EVENT"}
                    # self.is_rerun_required = False
                    tgt_event = deepcopy(src_event)

                backtrack = False
                if not tgt_event:
                    try:
                        dom, pkg, act = self.execute_target_events([])
                    except:  # selenium.common.exceptions.NoSuchElementException
                        # a23-a21-b21, a24-a21-b21: selected an EditText which is not editable
                        print(f'Backtrack to the previous step due to an exception in execution.')
                        invalid_event = self.tgt_events[-1]
                        self.current_src_index -= 1
                        # pop tgt_events
                        if self.current_src_index == 0:
                            self.tgt_events = []
                        else:
                            self.tgt_events = self.tgt_events[:self.idx_src_to_tgt[self.current_src_index - 1] + 1]
                        self.invalid_events[self.current_src_index].append(deepcopy(invalid_event))
                        continue

                    self.cache_seen_widgets(dom, pkg, act)

                    w_candidates = []
                    num_to_check = 10
                    if src_event['action'][0] == 'wait_until_text_invisible':
                        if not self.nearest_button_to_text:
                            tgt_event = Explorer.generate_empty_event(src_event['event_type'])
                        else:
                            w_candidates = WidgetUtil.most_similar(self.nearest_button_to_text, self.widget_db.values(),
                                                                   self.config.use_stopwords,
                                                                   self.config.expand_btn_to_text,
                                                                   self.config.cross_check)
                            num_to_check = 1  # we know the button exists, so no need to seek other similar ones
                    else:
                        w_candidates = WidgetUtil.most_similar(src_event, self.widget_db.values(),
                                                               self.config.use_stopwords,
                                                               self.config.expand_btn_to_text,
                                                               self.config.cross_check)

                    # if w_candidates:
                    #     w_candidates = self.decay_by_distance(w_candidates, pkg, act)
                    for i, (w, _) in enumerate(w_candidates[:num_to_check]):
                        # encode-decode: for some weird chars in a1 apps
                        print(f'({i+1}/{num_to_check}) Validating Similar w: {w}'.encode("utf-8").decode("utf-8"))
                        # skip invalid events
                        if any([WidgetUtil.is_equal(w, e) for e in self.invalid_events.get(self.current_src_index, [])]):
                            print('Skip a known broken event:', w)
                            continue
                        # skip widget with empty attribute if the action is wait_until with the attribute; a33-a35-b31
                        if src_event['action'][0] == 'wait_until_element_presence':
                            is_empty_atc = False
                            attrs_to_check = set(WidgetUtil.FEATURE_KEYS).difference({'clickable', 'password', 'naf'})
                            for atc in attrs_to_check:
                                if not w[atc]:
                                    atc_in_oracle = 'id' if atc == 'resource-id' else atc
                                    if src_event['action'][2] == atc_in_oracle:
                                        is_empty_atc = True
                                        break
                                    # a31-a33-b31; 'action': ['wait_until_element_presence', 10, 'xpath',
                                    #                         '//android.widget.TextView[@content-desc=""]']
                                    elif src_event['action'][2] == 'xpath' and '@'+atc in src_event['action'][3]:
                                        is_empty_atc = True
                                        break
                            if is_empty_atc:
                                print('Skip the widget without the attribute that the action is waiting for')
                                continue
                        try:
                            match = self.check_reachability(w, pkg, act)
                        except Exception as excep:
                            print(excep)
                            traceback.print_exc()
                            return False, self.current_src_index
                        if match:
                            # Never map two src EditText to the same tgt EditText, e.g., a51-a52-b52
                            if match['class'] == 'android.widget.EditText' and 'send_keys' in src_event['action'][0]:
                                if self.check_skipped(match):
                                    print(f'Duplicated match (later): {match}\n. Skipped.')
                                    continue
                                is_mapped, tgt_idx, src_idx = self.check_mapped(match)
                                # exact identical EditText in src_events, e.g., a12-a11-b12
                                is_idential_src_widgets = self.check_identical_src_widgets(src_idx, self.current_src_index)
                                if is_mapped and not is_idential_src_widgets:
                                    if match['score'] <= self.tgt_events[tgt_idx]['score']:
                                        print(f'Duplicated match (previous): {match}\n. Skipped.')
                                        continue  # discard this match
                                    else:
                                        print(f'Duplicated match. Backtrack to src_idx: {src_idx} to find another match')
                                        backtrack = True
                                        self.current_src_index = src_idx
                                        self.skipped_match[src_idx].append(deepcopy(self.tgt_events[tgt_idx]))
                                        # pop tgt_events
                                        if src_idx == 0:
                                            self.tgt_events = []
                                        else:
                                            self.tgt_events = self.tgt_events[:self.idx_src_to_tgt[src_idx-1] + 1]
                                        break
                            if 'clickable' not in w:  # a static widget
                                self.widget_db.pop(WidgetUtil.get_widget_signature(w), None)
                            if src_event['action'][0] == 'wait_until_text_invisible':
                                if self.runner.check_text_invisible(src_event):
                                    tgt_event = self.generate_event(match, deepcopy(src_event['action']))
                                else:
                                    tgt_event = Explorer.generate_empty_event(src_event['event_type'])
                            else:
                                tgt_event = self.generate_event(match, deepcopy(src_event['action']))
                            break
                if backtrack:
                    continue

                if not tgt_event:
                    tgt_event = Explorer.generate_empty_event(src_event['event_type'])

                # additional exploration (ATG and widget_db update) for empty oracle (e.g., a51-a53-b51)
                if tgt_event['class'] == 'EMPTY_EVENT' and tgt_event['event_type'] == 'oracle' and not is_explored:
                    print('Empty event for an oracle. Try to explore the app')
                    self.reset_and_explore(self.tgt_events)
                    is_explored = True
                    continue
                else:
                    is_explored = False

                print('** Learned for this step:')
                if 'stepping_events' in tgt_event and tgt_event['stepping_events']:
                    self.tgt_events += tgt_event['stepping_events']
                    for t in tgt_event['stepping_events']:
                        print(t)
                print(tgt_event)
                print('--')
                self.tgt_events.append(tgt_event)
                self.idx_src_to_tgt[self.current_src_index] = len(self.tgt_events) - 1
                self.current_src_index += 1

            self.f_target = self.fitness(self.tgt_events)
            print(f'Current target events with fitness {self.f_target}:')
            for t in self.tgt_events:
                print(t)
            self.snapshot()

            # if self.f_target == 0 (all events in self.tgt_events are EMPTY_EVENT)
            # update ATG and widget_db by a systematic exploration and start over
            if self.f_target == self.f_prev_target == 0:
                print('All Empty Events. Explore the app and start over.')
                self.reset_and_explore()
                self.tgt_events = []
                self.prev_tgt_events = []
                self.f_prev_target = -1

        return True, 0

    def reset_and_explore(self, tgt_events=[]):
        """Reset current state to the one after executing tgt_events
           and update ATG and widget_db by systematic exploration
        """
        self.runner.perform_actions(tgt_events, reset=True)  # reset app
        all_widgets = WidgetUtil.find_all_widgets(self.runner.get_page_source(),
                                                  self.runner.get_current_package(),
                                                  self.runner.get_current_activity(),
                                                  self.config.pkg_to)
        btn_widgets = []
        for w in all_widgets:
            if w['class'] in ['android.widget.Button', 'android.widget.ImageButton', 'android.widget.TextView']:
                attrs_to_check = set(WidgetUtil.FEATURE_KEYS).difference({'class', 'clickable', 'password'})
                attr_check = [attr in w and w[attr] for attr in attrs_to_check]
                if w['clickable'] == 'true' and any(attr_check):
                    btn_widgets.append(w)
        for btn_w in btn_widgets:
            self.runner.perform_actions(tgt_events, reset=True)
            btn_w['action'] = ['click']
            self.runner.perform_actions([btn_w], reset=False, cgp=self.cgp)
            self.cache_seen_widgets(self.runner.get_page_source(),
                                    self.runner.get_current_package(),
                                    self.runner.get_current_activity())

    def cache_seen_widgets(self, dom, pkg, act):
        current_widgets = WidgetUtil.find_all_widgets(dom, pkg, act, self.config.pkg_to)
        # print('** before:', self.widget_db)
        for w in current_widgets:
            w_signature = WidgetUtil.get_widget_signature(w)

            # remove the widget from sa info if already seen here
            w_sa = {k: v for k, v in w.items() if k not in ['clickable', 'password']}
            w_sa_signature = WidgetUtil.get_widget_signature(w_sa)
            popped = self.widget_db.pop(w_sa_signature, None)
            if popped:
                print('** wDB (SA) popped:', popped)

            # remove useless email fields with obsolete email address
            tmp_email = self.runner.databank.get_temp_email(renew=False)
            if tmp_email in w_signature:
                pre = w_signature.split(tmp_email)[0]
                if not pre.endswith('!'):
                    pre = pre.replace(pre.split('!')[-1], '', 1)
                post = w_signature.split(tmp_email)[-1]
                if not post.startswith('!'):
                    post = post.replace(post.split('!')[0], '', 1)
                discarded_keys = []
                for k in self.widget_db.keys():
                    if k.startswith(pre) and k.endswith(post) and k != pre + post:
                        if StrUtil.is_contain_email(self.widget_db[k]['text']):
                            discarded_keys.append(k)
                for k in discarded_keys:
                    popped = self.widget_db.pop(k, None)
                    if popped:
                        print('** wDB (obsolete Email) popped:', popped)

            # print('** wDB updated:', w)
            self.widget_db[w_signature] = w
        # print('** after:', self.widget_db)

    def execute_target_events(self, stepping_events):
        src_event = self.src_events[self.current_src_index]
        require_wait = src_event['action'][0].startswith('wait_until')
        # require_wait = True
        # if self.is_rerun_required:
        self.runner.perform_actions(self.tgt_events, require_wait, reset=True, cgp=self.cgp)
        # elif not self.is_rerun_required and self.tgt_events:
        #     # no reset and rerun, just execute the last matched action
        #     self.runner.perform_actions([self.tgt_events[-1]], require_wait, reset=False, cgp=self.cgp)
        self.runner.perform_actions(stepping_events, require_wait, reset=False, cgp=self.cgp)
        return self.runner.get_page_source(), self.runner.get_current_package(), self.runner.get_current_activity()

    @staticmethod
    def generate_event(w, actions=None):
        # if the action is wait_until_presence, change the content-desc/text/id to that of target app
        # e.g., ['wait_until_element_presence', 10, 'xpath', '//*[@content-desc="Open Menu"]']
        if actions[0] == 'wait_until_element_presence':
            if actions[2] == 'xpath' and '@content-desc=' in actions[3]:
                pre, post = actions[3].split('@content-desc=')
                post = f'@content-desc="{w["content-desc"]}"' + ''.join(post.split('"')[2:])
                actions[3] = pre + post
            elif actions[2] == 'xpath' and '@text=' in actions[3]:
                pre, post = actions[3].split('@text=')
                post = f'@text="{w["text"]}"' + ''.join(post.split('"')[2:])
                actions[3] = pre + post
            elif actions[2] == 'xpath' and 'contains(@text,' in actions[3]:
                pre, post = actions[3].split('contains(@text,')
                post = f'contains(@text, "{w["text"]}"' + ''.join(post.split('"')[2:])
                actions[3] = pre + post
            elif actions[2] == 'id':
                actions[3] = w['resource-id']
        w['action'] = actions
        return w

    @staticmethod
    def generate_empty_event(event_type):
        return {"class": "EMPTY_EVENT", 'score': 0, 'event_type': event_type}

    def check_reachability(self, w, current_pkg, current_act):
        # print(f'Validating Similar w: {w}')
        # dom, pkg, act = self.execute_target_events([])
        act_from = current_pkg + current_act
        act_to = w['package'] + w['activity']
        potential_paths = self.cgp.get_paths_between_activities(act_from, act_to, self.consider_naf_only_widget)
        if w['activity'] == current_act:
            potential_paths.insert(0, [])
        print(f'Activity transition: {act_from} -> {act_to}. {len(potential_paths)} paths to validate.')
        invalid_paths = []
        for ppath in potential_paths:
            match = self.validate_path(ppath, w, invalid_paths)
            if match:
                return match
        return None

    def validate_path(self, ppath, w_target, invalid_paths):
        path_show = []
        for hop in ppath:
            if '(' in hop:  # a GUI event
                if hop.startswith('D@'):
                    gui = ' '.join(hop.split()[:-1])
                else:
                    gui = self.rp.get_wName_from_oId(hop.split()[0])
                path_show.append(gui)
            else:
                path_show.append(StrUtil.get_activity((hop)))
        print(f'Validating path: ', path_show)

        # prune verified wrong path
        for ip in invalid_paths:
            if ip == ppath[:len(ip)]:
                print('Known invalid path prefix:', ppath[:len(ip)])
                return None

        # start follow the path to w_target
        _, __, ___ = self.execute_target_events([])
        stepping = []
        for i, hop in enumerate(ppath):
            if '(' in hop:  # a GUI event
                w_id = ' '.join(hop.split()[:-1])
                action = hop.split('(')[1][:-1]
                action = 'long_press' if action in ['onItemLongClick', 'onLongClick'] else 'click'
                if w_id.startswith('D@'):  # from dynamic exploration
                    # e.g., 'D@class=android.widget.Button&resource-id=org.secuso.privacyfriendlytodolist:id/btn_skip&text=Skip&content-desc='
                    kv_pairs = w_id[2:].split('&')
                    kv = [kvp.split('=') for kvp in kv_pairs]
                    criteria = {k: v for k, v in kv}
                    print('D@criteria:', criteria)
                    w_stepping = WidgetUtil.locate_widget(self.runner.get_page_source(), criteria)
                else:  # from static analysis
                    w_name = self.rp.get_wName_from_oId(w_id)
                    w_stepping = WidgetUtil.locate_widget(self.runner.get_page_source(), {'resource-id': w_name})
                if not w_stepping:
                    # add current path prefix to invalide path
                    is_existed = False
                    for ip in invalid_paths:
                        if ip == ppath[:i+1]:
                            is_existed = True
                    if not is_existed:
                        invalid_paths.append([h for h in ppath[:i+1]])
                    return None
                w_stepping['action'] = [action]
                w_stepping['activity'] = self.runner.get_current_activity()
                w_stepping['package'] = self.runner.get_current_package()
                w_stepping['event_type'] = 'stepping'
                stepping.append(w_stepping)
                act_from = self.runner.get_current_package() + self.runner.get_current_activity()
                self.runner.perform_actions([stepping[-1]], require_wait=False, reset=False, cgp=self.cgp)
                self.cache_seen_widgets(self.runner.get_page_source(),
                                        self.runner.get_current_package(),
                                        self.runner.get_current_activity())
                act_to = self.runner.get_current_package() + self.runner.get_current_activity()
                self.cgp.add_edge(act_from, act_to, w_stepping)

        # check if the target widget exists
        # if self.runner.get_current_activity() not in ppath[-1]:
        #     return None
        attrs_to_check = set(WidgetUtil.FEATURE_KEYS).difference({'clickable', 'password'})
        criteria = {k: w_target[k] for k in attrs_to_check if k in w_target}
        # for text_presence oracle, force the text to be the same as the src_event
        if self.src_events[self.current_src_index]['action'][0] == 'wait_until_text_presence':
            criteria['text'] = self.src_events[self.current_src_index]['action'][3]
        # for confirm email: if both prev and current src_action are input email
        if self.current_src_index > 0 and self.is_for_email_or_pwd(self.src_events[self.current_src_index-1],
                                                                   self.src_events[self.current_src_index]):
            # for the case of matching to the only one email field
            if StrUtil.is_contain_email(self.src_events[self.current_src_index]['action'][1]):
                criteria['text'] = self.runner.databank.get_temp_email(renew=False)
        w_tgt = WidgetUtil.locate_widget(self.runner.get_page_source(), criteria)
        if not w_tgt:
            return None
        else:
            src_event = self.src_events[self.current_src_index]
            w_tgt['stepping_events'] = stepping
            w_tgt['package'] = self.runner.get_current_package()
            w_tgt['activity'] = self.runner.get_current_activity()
            w_tgt['event_type'] = src_event['event_type']
            w_tgt['score'] = WidgetUtil.weighted_sim(w_tgt, src_event)
            if src_event['action'][0] == 'wait_until_text_invisible':
                # here, w_tgt is the nearest button to the text. Convert it to the oracle event
                for k in w_tgt.keys():
                    if k not in ['stepping_events', 'package', 'activity', 'event_type', 'score']:
                        w_tgt[k] = ''

            if src_event['action'][0] == 'wait_until_text_presence':
                # cache the closest button on the current screen for possible text_invisible oracle in the future
                self.nearest_button_to_text = WidgetUtil.get_nearest_button(self.runner.get_page_source(), w_tgt)
                self.nearest_button_to_text['activity'] = w_tgt['package']
                self.nearest_button_to_text['package'] = w_tgt['activity']

            return w_tgt

    @staticmethod
    def fitness(events):
        gui_scores = [float(e['score']) for e in events if e['event_type'] == 'gui']
        oracle_scores = [float(e['score']) for e in events if e['event_type'] == 'oracle']
        gui = mean(gui_scores) if gui_scores else 0
        oracle = mean(oracle_scores) if oracle_scores else 0
        return 0.5*gui + 0.5*oracle
    
    def __reduce__(self):
        attributes_to_exclude = ('socket','config', 'runner')
        state = self.__dict__.copy()
        for attr in attributes_to_exclude:
            if str(attr) in state:
                del state[attr]

        return (self.__class__, (), state)

    def snapshot(self):
        with open(os.path.join(SNAPSHOT_FOLDER, self.config.id + '.pkl'), 'wb') as f:
            pickle.dump(self, f)

    def check_mapped(self, match):
        tgt_idx = -1
        for i, e in enumerate(self.tgt_events):
            if e['class'] != 'android.widget.EditText' or 'send_keys' not in e['action'][0]:
                continue
            e_tgt_new_text = deepcopy(e)
            e_tgt_new_text['text'] = e_tgt_new_text['action'][1]
            # todo: ensure that e and match are on the same screen
            if WidgetUtil.is_equal(match, e) or WidgetUtil.is_equal(match, e_tgt_new_text):
                tgt_idx = i
                break
        if tgt_idx == -1:
            return False, -1, -1
        else:
            src_idx = -1
            for i_src, i_tgt in self.idx_src_to_tgt.items():
                if i_tgt == tgt_idx:
                    src_idx = i_src
                    break
            assert src_idx != -1
            return True, tgt_idx, src_idx

    def check_skipped(self, match):
        for skipped in self.skipped_match[self.current_src_index]:
            skipped_new_text = deepcopy(skipped)
            skipped_new_text['text'] = skipped_new_text['action'][1]
            if WidgetUtil.is_equal(match, skipped) or WidgetUtil.is_equal(match, skipped_new_text):
                return True
        return False

    def check_identical_src_widgets(self, src_idx1, src_idx2):
        """ True: treat two src widgets as the same, i.e., not to check identical mapping.
            e.g., a15-a11-b12 or a31-a32-b31 (for confirm email/password EditText)
        """
        if src_idx1 == -1 or src_idx2 == -1:
            return True
        src_e1 = self.src_events[src_idx1]
        src_e2 = self.src_events[src_idx2]
        src_classes_to_check = ['android.widget.EditText', 'android.widget.MultiAutoCompleteTextView']
        if src_e1['class'] in src_classes_to_check and src_e2['class'] in src_classes_to_check:
            if self.is_for_email_or_pwd(src_e1, src_e2):
                return True
            else:
                w1 = deepcopy(src_e1)
                w1['text'] = ''
                w2 = deepcopy(src_e2)
                w2['text'] = ''
                return WidgetUtil.is_equal(w1, w2)
        else:
            return True

    def is_for_email_or_pwd(self, src_e1, src_e2):
        if 'send_keys' in src_e1['action'][0] and 'send_keys' in src_e2['action'][0]:
            if src_e1['action'][1] == src_e2['action'][1]:
                if StrUtil.is_contain_email(src_e1['action'][1]) or \
                        src_e1['action'][1] == self.runner.databank.get_password():
                    return True
        return False

    def decay_by_distance(self, w_candidates, current_pkg, current_act):
        new_candidates = []
        for w, score in w_candidates:
            act_from = current_pkg + current_act
            act_to = w['package'] + w['activity']
            if act_from == act_to:
                d = 1
            else:
                potential_paths = self.cgp.get_paths_between_activities(act_from, act_to, self.consider_naf_only_widget)
                if not potential_paths:
                    d = 2
                else:
                    shortest_path, shortest_d = potential_paths[0], len(potential_paths[0])
                    for ppath in potential_paths[1:]:
                        if len(ppath) < shortest_d:
                            shortest_path, shortest_d = ppath, len(ppath)
                    d = len([hop for hop in shortest_path if '(' in hop or 'D@' in hop])  # number of GUI events
                    assert d >= 1
            new_score = score / (1 + math.log(d, 2))
            new_candidates.append((w, new_score))
        new_candidates.sort(key=lambda x: x[1], reverse=True)
        if [s for w, s in w_candidates[:10]] != [s for w, s in new_candidates[:10]]:
            print('** Similarity rank changed after considering distance')
        return new_candidates


if __name__ == '__main__':
    # python Explorer.py a25-a22-b21 1 5723 emulator-5556 2>&1 | tee log\1-step\a25-a22-b21.txt
    if len(sys.argv) > 1:
        config_id = sys.argv[1]
        # lookahead_step = int(sys.argv[2])
        appium_port = sys.argv[2]
        udid = sys.argv[3]
    else:
        config_id = 'a33-a35-b31'
        # lookahead_step = 1
        appium_port = '5723'
        udid = 'emulator-5556'

    LOAD_SNAPSHOT = True
    # LOAD_SNAPSHOT = False
    if os.path.exists(os.path.join(SNAPSHOT_FOLDER, config_id + '.pkl')) and LOAD_SNAPSHOT:
        with open(os.path.join(SNAPSHOT_FOLDER, config_id + '.pkl'), 'rb') as f:
            explorer = pickle.load(f)
            # for n in explorer.cgp.G.nodes:
            #     print(n)
            # for e in explorer.cgp.G.edges:
            #     print(e, explorer.cgp.G.edges[e]['label'])
            # for k, v in explorer.cgp.self_loops.items():
            #     print(k)
            #     for l in v:
            #         print(l)
            print(f'Snapshot loaded. Cached target events (fitness: {explorer.f_target}):')
            for e in explorer.tgt_events:
                print(e)
            print(f'Prev target events (fitness: {explorer.f_prev_target})')
            for e in explorer.prev_tgt_events:
                print(e)
            print(f'Widget DB ({len(explorer.widget_db)})')
            for k, v in explorer.widget_db.items():
                print(k, v)
            print(f'# nodes: {len(explorer.cgp.G.nodes)}, # edges: {len(explorer.cgp.G.edges)}')
            print(f'self loops: {explorer.cgp.self_loops}')
            print(explorer.skipped_match)
            print(explorer.nearest_button_to_text)
            # input()
            explorer.runner = Runner(explorer.config.pkg_to, explorer.config.act_to, explorer.config.no_reset, appium_port, udid)
            # explorer.f_target = 0.55

    else:
        explorer = Explorer(config_id, appium_port, udid)

    t_start = time.time()
    # explorer.mutate_src_action({'long_press': 'swipe_right', 'swipe_right': 'long_press'})
    is_done, failed_step = explorer.run()
    if is_done:
        print('Finished. Learned actions')
        if explorer.f_prev_target > explorer.f_target:
            results = explorer.prev_tgt_events
        else:
            results = explorer.tgt_events
        for a in results:
            print(a)
        print(f'Transfer time in sec: {time.time() - t_start}')
        # input('wait clear')
        print(f'Start testing learned actions')
        t_start = time.time()
        try:
            explorer.runner.perform_actions(results)
            print(f'Testing time in sec: {time.time() - t_start}')
        except Exception as excep:
            print(f'Error when validating learned actions\n{excep}')
    else:
        print(f'Failed transfer at source index {failed_step}')
        print(f'Transfer time in sec: {time.time() - t_start}')
        results = explorer.tgt_events
    Util.save_events(results, config_id)

