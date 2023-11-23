from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import re
# local import
from StrUtil import StrUtil


class WidgetUtil:
    # NAF means "Not Accessibility Friendly", e.g., a back button without any textual info like content-desc
    FEATURE_KEYS = ['class', 'resource-id', 'text', 'content-desc', 'clickable', 'password', 'naf']
    WIDGET_CLASSES = ['android.widget.EditText', 'android.widget.MultiAutoCompleteTextView', 'android.widget.TextView',
                      'android.widget.Button', 'android.widget.ImageButton', 'android.view.View']
    state_to_widgets = {}  # for a gui state, there are "all_widgets": a list of all widgets, and
                           # "most_similar_widgets": a dict for a source widget and the list of its most similar widgets and scores

    @staticmethod
    def get_gui_signature(xml_dom, pkg_name, act_name):
        """Get the signature for a GUI state by the package/activity name and the xml hierarchy
        Breadth first traversal for the non-leaf/leaf nodes and their cumulative index sequences
        """
        xml_dom = re.sub(r'&#\d+;', "", xml_dom)  # remove emoji
        root = ET.fromstring(xml_dom)
        queue = [(root, '0')]
        layouts = []
        executable_leaves = []
        while queue:
            node, idx = queue.pop()
            if len(list(node)):  # the node has child(ren)
                layouts.append(idx)
                for i, child in enumerate(node):
                    queue.insert(0, (child, idx + '-' + str(i)))
            else:  # a leaf node
                executable_leaves.append(idx)
        # print(layouts)
        # print(executable_leaves)
        sign = [pkg_name, act_name, '+'.join(layouts), '+'.join(executable_leaves)]
        return '!'.join(sign)

    @classmethod
    def get_widget_signature(cls, w):
        """Get the signature for a GUI widget by its attributes"""
        sign = []
        for k in cls.FEATURE_KEYS + ['package', 'activity']:
            if k in w:
                sign.append(w[k])
            else:
                sign.append('')
        return '!'.join(sign)

    @classmethod
    def get_most_similar_widget_from_cache(cls, gui_signature, widget_signature):
        """Return the most similar widget and the score to the source widget in a gui state in cache"""
        if gui_signature not in cls.state_to_widgets:
            return None, -1
        if 'most_similar_widgets' in cls.state_to_widgets[gui_signature]:
            if widget_signature in cls.state_to_widgets[gui_signature]['most_similar_widgets']:
                # print('Cache HIT from SIMILAR')
                return cls.state_to_widgets[gui_signature]['most_similar_widgets'][widget_signature][0]
        return None, -1

    @classmethod
    def get_all_widgets_from_cache(cls, gui_signature):
        """Return all widgets in a gui state in cache"""
        if gui_signature in cls.state_to_widgets and 'all_widgets' in cls.state_to_widgets[gui_signature]:
            # print('Cache HIT from ALL')
            return cls.state_to_widgets[gui_signature]['all_widgets']
        else:
            return None

    @staticmethod
    def get_parent_text(soup_ele):
        # consider immediate parent node's text if exists
        parent_text = ''
        parent = soup_ele.find_parent()
        if parent and 'text' in parent.attrs and parent['text']:
            parent_text += parent['text']
        # consider grandparent if it's TextInputLayout (for ? related apps)
        parent = parent.find_parent()
        if parent and 'text' in parent.attrs and parent['text'] and parent['class'][0] == 'TextInputLayout':
            parent_text += parent['text']
        return parent_text

    @staticmethod
    def get_sibling_text(soup_ele):
        # (for Tip related apps)
        # consider immediate previous sibling text if exists and the parent is LinearLayout
        sibling_text = ''
        parent = soup_ele.find_parent()
        if parent and parent['class'][0] in ['android.widget.LinearLayout', 'android.widget.RelativeLayout']:
            prev_sib = soup_ele.previous_sibling
            if prev_sib and 'text' in prev_sib.attrs and prev_sib['text']:
                sibling_text = prev_sib['text']
        return sibling_text

    @classmethod
    def get_attrs(cls, dom, attr_name, attr_value, tag_name=''):
        soup = BeautifulSoup(dom, 'lxml-xml')
        if attr_name == 'text-contain':
            cond = {'text': lambda x: x and attr_value in x}
        else:
            cond = {attr_name: attr_value}
        if tag_name:
            cond['class'] = tag_name
        ele = soup.find(attrs=cond)
        #for k, v in ele.attrs.items():
        #    print(k, v)
        d = {}
        for key in cls.FEATURE_KEYS:
            d[key] = ele.attrs[key] if key in ele.attrs else ""
            if key == 'class':
                d[key] = d[key][0]  # for now, only consider the first class
            elif key == 'clickable' and key in ele.attrs and ele.attrs[key] == 'false':
                d[key] = WidgetUtil.propagate_clickable(ele)
        d['parent_text'] = WidgetUtil.get_parent_text(ele)
        d['sibling_text'] = WidgetUtil.get_sibling_text(ele)
        return d

    @classmethod
    def get_empty_attrs(cls):
        d = {}
        for key in cls.FEATURE_KEYS:
            d[key] = ""
        d['parent_text'] = ""
        d['sibling_text'] = ""
        return d

    @classmethod
    def find_all_widgets(cls, dom, pkg, act, target_pkg, update_cache=True):
        if 'com.android.launcher' in pkg:  # the app is closed
            return []

        if pkg != target_pkg:  # exclude all widgets not belonging to the app's package
            return []

        if act.startswith('com.facebook'):  # the app reaches facebook login, out of the app's scope
            return []

        gui_signature = WidgetUtil.get_gui_signature(dom, pkg, act)
        if not update_cache:
            widgets = WidgetUtil.get_all_widgets_from_cache(gui_signature)
            if widgets:
                return widgets

        soup = BeautifulSoup(dom, 'lxml-xml')
        widgets = []
        for w_class in cls.WIDGET_CLASSES:
            elements = soup.find_all(attrs={'class': w_class})
            for e in elements:
                d = cls.get_widget_from_soup_element(e)
                if d:
                    if 'yelp' in gui_signature and 'text' in d and d['text'] == 'Sign up with Google':
                        d['text'] = 'SIGN UP WITH GOOGLE'  # Specific for Yelp
                    d['package'], d['activity'] = pkg, act
                    widgets.append(d)

        if widgets or update_cache:
            cls.state_to_widgets[gui_signature] = {'all_widgets': widgets, 'most_similar_widgets': {}}
        return widgets

    @classmethod
    def get_widget_from_soup_element(cls, e):
        if not e:
            return None
        d = {}
        if 'enabled' in e.attrs and e['enabled'] == 'true':
            for key in cls.FEATURE_KEYS:
                d[key] = e.attrs[key] if key in e.attrs else ''
                if key == 'class':
                    d[key] = d[key].split()[0]  # for now, only consider the first class
                elif key == 'clickable' and key in e.attrs and e.attrs[key] == 'false':
                    d[key] = WidgetUtil.propagate_clickable(e)
                elif key == 'resource-id':
                    rid = d[key].split('/')[-1]
                    prefix = ''.join(d[key].split('/')[:-1])
                    d[key] = rid
                    d['id-prefix'] = prefix + '/' if prefix else ''
            d['parent_text'] = WidgetUtil.get_parent_text(e)
            d['sibling_text'] = WidgetUtil.get_sibling_text(e)
            return d
        else:
            return None

    @classmethod
    def propagate_clickable(cls, soup_element):
        # clickable propagation from immediate parent
        parent = soup_element.find_parent()
        if 'clickable' in parent.attrs and parent['clickable'] == 'true':
            return 'true'
        for i in range(2):  # a22-a23-b22 (mutated)
            parent = parent.find_parent()
            if parent and 'class' in parent.attrs and parent['class'][0] in ['android.widget.ListView']:
                if 'clickable' in parent.attrs and parent['clickable'] == 'true':
                    return 'true'
        return 'false'

    # @classmethod
    # def most_similar_widget(cls, current_widgets, src_event, dom, pkg, act,
    #                         use_stopwords=True, expand_btn_to_text=False, cross_check=False,
    #                         extra_score=0, update_cache=True):
    #     # if target_action['class'] == 'SYS_EVENT':
    #     #     return {'class': 'SYS_EVENT'}, 1
    #     gui_signature = WidgetUtil.get_gui_signature(dom, pkg, act)
    #     src_widget_signature = WidgetUtil.get_widget_signature(src_event)
    #     if not update_cache:
    #         w_res, score = WidgetUtil.get_most_similar_widget_from_cache(gui_signature, src_widget_signature)
    #         if w_res:
    #             return w_res, score
    #
    #     src_class = src_event['class']
    #     is_clickable = src_event['clickable']  # string
    #     is_password = src_event['password']  # string
    #     pairs = []
    #     if src_class in ['android.widget.ImageButton', 'android.widget.Button']:
    #         if expand_btn_to_text:
    #             src_class = ['android.widget.ImageButton', 'android.widget.Button', 'android.widget.TextView']
    #         else:
    #             src_class = ['android.widget.ImageButton', 'android.widget.Button']
    #     elif src_class == 'android.widget.TextView' and is_clickable == 'true':
    #         src_class = ['android.widget.ImageButton', 'android.widget.Button', 'android.widget.TextView']
    #     elif src_class == 'android.widget.EditText' and src_event['action'][0].startswith('wait_until'):
    #         # for tip apps, e.g., a51-a53-b51
    #         src_class = ['android.widget.EditText', 'android.widget.TextView']
    #     else:
    #         src_class = [src_class]
    #     for w in current_widgets:
    #         if w['class'] in src_class and w['password'] == is_password:
    #             if w['clickable'] == is_clickable:
    #                 score = WidgetUtil.weighted_sim(w, src_event, use_stopwords=use_stopwords, cross_check=cross_check)
    #                 # corner case for the password field in Target app registration
    #                 if not score and is_password == 'true' and not (w['text'] or w['resource-id'] or w['content-desc']) \
    #                         and w['class'] == 'android.widget.EditText':
    #                     score = 1.0
    #             elif src_event['action'][0].startswith('wait_until') and w['class'] in ['android.widget.EditText', 'android.widget.TextView']:
    #                 # if checking oracle, no need to check clickable consistence for TextView and EditText
    #                 # (for tip apps, e.g., a51-a51-b51 and a51-a53-b51)
    #                 score = WidgetUtil.weighted_sim(w, src_event, use_stopwords=use_stopwords, cross_check=cross_check)
    #             elif src_event['action'][0].startswith('swipe') and w['class'] in ['android.widget.TextView']:
    #                 # corner case for a21-a25-b22; no need to check clickable consistence for TextView and swipe action
    #                 score = WidgetUtil.weighted_sim(w, src_event, use_stopwords=use_stopwords, cross_check=cross_check)
    #             else:
    #                 score = None
    #             if score:
    #                 score = min(1.0, score + extra_score)
    #                 pairs.append((w, score))
    #
    #     pairs = sorted(pairs, key=lambda x: x[1], reverse=True)
    #     if pairs:
    #         '''
    #         for p in pairs:
    #             print(p[0], p[1])
    #         input('DUMP')
    #         '''
    #         candidate_pairs = [p for p in pairs if p[1] == pairs[0][1]]
    #         ans = WidgetUtil.advanced_select(candidate_pairs, src_event)
    #         assert gui_signature in cls.state_to_widgets
    #         # assert src_widget_signature not in cls.state_to_widgets[gui_signature]['most_similar_widgets']
    #         cls.state_to_widgets[gui_signature]['most_similar_widgets'][src_widget_signature] = [ans]
    #         return ans[0], ans[1]
    #     if update_cache:
    #         assert gui_signature in cls.state_to_widgets
    #         cls.state_to_widgets[gui_signature]['most_similar_widgets'][src_widget_signature] = [(None, -1)]
    #     return None, -1

    @staticmethod
    def advanced_select(sim_pairs, src_event):
        # If there are 1+ widgets with the same sim score,
        # pick the one with the most words in common with the target text
        if len(sim_pairs) == 1:
            return sim_pairs[0]
        ans = sim_pairs[0]
        src_text = src_event['text']
        if src_text:
            overlap_score = -1
            for p in sim_pairs:
                w_text = p[0]['text']
                if w_text:
                    s1 = set(src_text.lower().strip().split())
                    s2 = set(w_text.lower().strip().split())
                    intersection = len(s1.intersection(s2))
                    if intersection > overlap_score:
                        overlap_score = intersection
                        ans = p
        return ans

    # @staticmethod
    # def weighted_sim_new(new_widget, old_widget, use_stopwords=True, cross_check=False):
    #     # cross check NL info in text and content-desc
    #     # consider sibling text and adjust weights for parent and sibling for tip apps
    #     attrs = ['resource-id', 'text', 'content-desc', 'parent_text', 'sibling_text']
    #     sent_new, sent_old = [], []
    #     for i, attr in enumerate(attrs):
    #         # if attr in new_widget and attr in old_widget:
    #         #     sent_new += StrUtil.tokenize(attr, new_widget[attr], use_stopwords=use_stopwords)
    #         #     sent_old += StrUtil.tokenize(attr, old_widget[attr], use_stopwords=use_stopwords)
    #         if attr in new_widget:
    #             sent_new += StrUtil.tokenize(attr, new_widget[attr], use_stopwords=use_stopwords)
    #         if attr in old_widget:
    #             sent_old += StrUtil.tokenize(attr, old_widget[attr], use_stopwords=use_stopwords)
    #     if sent_new and sent_old:
    #         # todo: specific for yelp: ['Log', 'In'] -> ['Login']
    #         sim = StrUtil.w2v_sent_sim(sent_new, sent_old)
    #         if sim:
    #             return sim
    #         else:
    #             return None
    #     else:
    #         return None

    @staticmethod
    def weighted_sim(new_widget, old_widget, use_stopwords=True, cross_check=False):
        # similarity score is computed by the textual info of the widgets and the activities they belong to
        # cross check NL info in text and content-desc
        # consider sibling text and adjust weights for parent and sibling for tip apps
        attrs = ['resource-id', 'text', 'content-desc', 'parent_text', 'sibling_text']

        # not to evaluate widget without textual info
        is_attr_existed_old = [a in old_widget and old_widget[a] for a in attrs]
        is_attr_existed_new = [a in new_widget and new_widget[a] for a in attrs]
        if not any(is_attr_existed_old) or not any(is_attr_existed_new):
            return None

        attrs_weights = [1, 1, 1, 1, 0.5]  # higher weights for 'main' info source; proportionate to the DOM distance
        w_scores = []
        for i, attr in enumerate(attrs):
            score = 0
            if attr in new_widget and attr in old_widget:
                s_new = StrUtil.tokenize(attr, new_widget[attr], use_stopwords=use_stopwords)
                s_new = StrUtil.expand_text(new_widget['class'], attr, s_new)
                s_old = StrUtil.tokenize(attr, old_widget[attr], use_stopwords=use_stopwords)
                s_old = StrUtil.expand_text(old_widget['class'], attr, s_old)
                if s_new and s_old:
                    sim = StrUtil.w2v_sent_sim(s_new, s_old)
                    if sim:
                        # if no text and no parent_text, sibling text is more important
                        # (a22-a23-b21: srcIdx 1; a25-a23-b21: srcIdx 1)
                        score = sim * attrs_weights[i]
                        if attr == 'sibling_text':
                            if not all([old_widget['text'] + old_widget['parent_text'],
                                        new_widget['text'] + new_widget['parent_text']]):
                            # if not old_widget['text'] and not old_widget['parent_text'] \
                            #         and not new_widget['text'] and not new_widget['parent_text']:
                                score = sim
            w_scores.append(score)

        # cross check parent_text and text
        text_attrs = ['text', 'parent_text']#, 'sibling_text']
        cross_score = -1
        for a1 in text_attrs:
            for a2 in text_attrs:
                if a1 != a2 and a1 in new_widget and new_widget[a1] and a2 in old_widget and old_widget[a2]:
                    s_new = StrUtil.tokenize(a1, new_widget[a1], use_stopwords=use_stopwords)
                    s_new = StrUtil.expand_text(new_widget['class'], a1, s_new)
                    s_old = StrUtil.tokenize(a2, old_widget[a2], use_stopwords=use_stopwords)
                    s_old = StrUtil.expand_text(old_widget['class'], a2, s_old)
                    if s_new and s_old:
                        sim = StrUtil.w2v_sent_sim(s_new, s_old)
                        if sim and sim > cross_score:
                            cross_score = sim
        if cross_score > -1:
            w_scores.append(cross_score)

        if not w_scores and cross_check:  # cross check the NL info (Target app registration)
            cross_score = -1
            for a1 in attrs:
                for a2 in attrs:
                    if a1 != a2 and a1 in new_widget and new_widget[a1] and a2 in old_widget and old_widget[a2]:
                        s_new = StrUtil.tokenize(a1, new_widget[a1], use_stopwords=use_stopwords)
                        s_new = StrUtil.expand_text(new_widget['class'], a1, s_new)
                        s_old = StrUtil.tokenize(a2, old_widget[a2], use_stopwords=use_stopwords)
                        s_old = StrUtil.expand_text(old_widget['class'], a2, s_old)
                        if s_new and s_old:
                            sim = StrUtil.w2v_sent_sim(s_new, s_old)
                            if sim and sim > cross_score:
                                cross_score = sim
            if cross_score > -1:
                w_scores.append(cross_score)

        state_score = StrUtil.w2v_sent_sim(
            StrUtil.tokenize('Activity', old_widget['activity'], use_stopwords=use_stopwords),
            StrUtil.tokenize('Activity', new_widget['activity'], use_stopwords=use_stopwords)
        )
        # state_score = state_score if state_score else -1
        # # weight_w, weight_state = 0.5, 0.5
        # weight_w, weight_state = 0.65, 0.35  # a31-a32-b31
        # if w_scores:
        #     return weight_w*(sum(w_scores)/len(w_scores)) + weight_state*state_score
        # else:
        #     return weight_state*state_score

        weight_state = 1
        state_score = state_score if state_score else 0
        state_score *= weight_state
        w_scores.append(state_score)
        return sum(w_scores) / len(w_scores)

    @classmethod
    def is_equal(cls, w1, w2, ignore_activity=False):
        if not w1 or not w2:
            return False
        keys_for_equality = set(cls.FEATURE_KEYS)
        keys_for_equality.remove('naf')
        if not ignore_activity:
            keys_for_equality = keys_for_equality.union({'package', 'activity'})
        for k in keys_for_equality:
            if (k in w1 and k not in w2) or (k not in w1 and k in w2):
                return False
            if k in w1 and k in w2:
                v1, v2 = w1[k], w2[k]
                if k == 'resource-id' and 'id-prefix' in w1:
                    v1 = w1['id-prefix'] + w1[k]
                if k == 'resource-id' and 'id-prefix' in w2:
                    v2 = w2['id-prefix'] + w2[k]
                if v1 != v2:
                    return False
        return True

    '''
    @staticmethod
    def get_state_feature(act_name, dom, use_stopwords=True):
        """Express a GUI state as:
        1. tokenized words of current Activity;
        2. # of clickable elements / android.widget.EditText widget / long-clickable elements
        """
        soup = BeautifulSoup(dom, 'lxml-xml')
        feature_vec = [
            len(soup.find_all(attrs={'clickable': 'true', 'enabled': 'true'})),
            len(soup.find_all(attrs={'class': 'android.widget.EditText', 'enabled': 'true'})),
            len(soup.find_all(attrs={'long-clickable': 'true', 'enabled': 'true'}))
        ]
        #denominator = sum(feature_vec)
        #if denominator > 0:
        #    feature_vec = [n/denominator for n in feature_vec]
        return {'act_name': str_util.tokenize('Activity', act_name, use_stopwords=use_stopwords), 'feature': feature_vec}
    '''

    @classmethod
    def locate_widget(cls, dom, criteria):
        # e.g., criteria =
        #   {'class': 'TextView', 'text': 'Okay', 'resource-id': 'tv_task', 'content-desc': ""} or
        #   {'class': 'android.widget.Button', 'resource-id': 'org.secuso.privacyfriendlytodolist:id/btn_skip'}
        regex_cria = {}
        for k, v in criteria.items():
            if v:
                v = v.replace('+', r'\+')  # for error when match special char '+'
                v = v.replace('?', r'\?')  # for error when match special char '?'
                if k == 'resource-id':
                    regex_cria[k] = re.compile(f'{v}$')
                else:
                    regex_cria[k] = re.compile(f'{v}')
        if not regex_cria:
            return None
        soup = BeautifulSoup(dom, 'lxml-xml')
        return cls.get_widget_from_soup_element(soup.find(attrs=regex_cria))

    @classmethod
    def most_similar(cls, src_event, widgets, use_stopwords=True, expand_btn_to_text=False, cross_check=False):
        src_class = src_event['class']
        is_clickable = src_event['clickable']  # string
        is_password = src_event['password']  # string
        similars = []
        # if src_class in ['android.widget.ImageButton', 'android.widget.Button']:
        #     if expand_btn_to_text:
        #         src_class = ['android.widget.ImageButton', 'android.widget.Button', 'android.widget.TextView']
        #     else:
        #         src_class = ['android.widget.ImageButton', 'android.widget.Button']
        # elif src_class == 'android.widget.TextView' and is_clickable == 'true':
        #     src_class = ['android.widget.ImageButton', 'android.widget.Button', 'android.widget.TextView']
        #     if re.search(r'https://\w+\.\w+', src_event['text']):  # e.g., a15-a1x-b12
        #         src_class.append('android.widget.EditText')
        # elif src_class == 'android.widget.TextView' and src_event['action'][0].startswith('wait_until_text_presence'):
        #     # e.g., a53-a51-b51, a53-a52-b51
        #     src_class = ['android.widget.TextView', 'android.widget.EditText']
        # elif src_class == 'android.widget.EditText' and src_event['action'][0].startswith('wait_until_text_presence'):
        #     # e.g., a51-a53-b51
        #     src_class = ['android.widget.EditText', 'android.widget.TextView']
        # elif src_class == 'android.widget.EditText' and re.search(r'https://\w+\.\w+', src_event['text']):
        #     # e.g., a11-a15-b12
        #     src_class = ['android.widget.EditText', 'android.widget.TextView']
        # elif src_class in ['android.widget.MultiAutoCompleteTextView', 'android.widget.TextView']:  # a41, a42 (b42)
        #     src_class = ['android.widget.MultiAutoCompleteTextView', 'android.widget.TextView']
        #     if 'send_keys' in src_event['action']:
        #         src_class.append('android.widget.EditText')
        # else:
        #     src_class = [src_class]
        tgt_classes = [src_class]
        if src_class in ['android.widget.ImageButton', 'android.widget.Button']:
            tgt_classes = ['android.widget.ImageButton', 'android.widget.Button']
            if expand_btn_to_text:
                tgt_classes.append('android.widget.TextView')
        elif src_class == 'android.widget.TextView':
            if is_clickable == 'true':
                tgt_classes += ['android.widget.ImageButton', 'android.widget.Button']
                if re.search(r'https://\w+\.\w+', src_event['text']):  # e.g., a15-a1x-b12
                    tgt_classes.append('android.widget.EditText')
            elif src_event['action'][0].startswith('wait_until_text_presence'):  # e.g., a53-a51-b51, a53-a52-b51
                tgt_classes.append('android.widget.EditText')
        elif src_class == 'android.widget.EditText':
            tgt_classes.append('android.widget.MultiAutoCompleteTextView')  # a43-a41-b42
            if src_event['action'][0].startswith('wait_until_text_presence'):  # e.g., a51-a53-b51
                tgt_classes.append('android.widget.TextView')
            elif re.search(r'https://\w+\.\w+', src_event['text']):  # e.g., a11-a15-b12
                tgt_classes.append('android.widget.TextView')
        elif src_class == 'android.widget.MultiAutoCompleteTextView':  # a41-a43-b42
            tgt_classes.append('android.widget.EditText')

        for w in widgets:
            need_evaluate = False
            if w['class'] in tgt_classes:
                if 'password' in w and w['password'] != is_password:
                    continue
                if 'clickable' in w:  # a dynamic widget                    
                    if w['clickable'] == is_clickable:
                        need_evaluate = True
                    elif 'action' in src_event and 'class' in w:
                        # if checking oracle, no need to check clickable consistence for TextView and EditText
                        # (e.g., a53-a51-b51 and a51-a53-b51)
                        if src_event['action'][0].startswith('wait_until') \
                                and w['class'] in ['android.widget.EditText', 'android.widget.TextView']:
                            need_evaluate = True                    
                        elif src_event['action'][0].startswith('swipe') and w['class'] in ['android.widget.TextView']:
                            # a21-a25-b22; no need to check clickable consistence for TextView and swipe action
                            need_evaluate = True
                else:  # a static widget
                    need_evaluate = True
            score = WidgetUtil.weighted_sim(w, src_event, use_stopwords, cross_check) if need_evaluate else None
            # if w['class'] in tgt_classes:
            #     print(w, score)
            if score:
                similars.append((w, score))
        similars.sort(key=lambda x: x[1], reverse=True)
        return similars

    @classmethod
    def get_nearest_button(cls, dom, w):
        # for now just return the first btn on the screen; todo: find the nearest button
        soup = BeautifulSoup(dom, 'lxml-xml')
        for btn_class in ['android.widget.ImageButton', 'android.widget.Button', 'android.widget.EditText']:
            all_btns = soup.find_all(attrs={'class': btn_class})
            if all_btns and len(all_btns) > 0:
                return cls.get_widget_from_soup_element(all_btns[0])
        return None
