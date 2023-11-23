import re
import requests
import json


class StrUtil:

    # stop words from nltk
    STOPWORDS = {'ourselves', 'hers', 'between', 'yourself', 'but', 'again', 'there', 'about', 'once', 'during',
                 'out', 'very', 'having', 'with', 'they', 'own', 'an', 'be', 'some', 'for', 'do', 'its', 'yours',
                 'such', 'into', 'of', 'most', 'itself', 'other', 'off', 'is', 's', 'am', 'or', 'who', 'as', 'from',
                 'him', 'each', 'the', 'themselves', 'until', 'below', 'are', 'we', 'these', 'your', 'his', 'through',
                 'don', 'nor', 'me', 'were', 'her', 'more', 'himself', 'this', 'down', 'should', 'our', 'their',
                 'while', 'above', 'both', 'up', 'to', 'ours', 'had', 'she', 'all', 'no', 'when', 'at', 'any',
                 'before', 'them', 'same', 'and', 'been', 'have', 'in', 'will', 'on', 'does', 'yourselves', 'then',
                 'that', 'because', 'what', 'over', 'why', 'so', 'can', 'did', 'not', 'now', 'under', 'he', 'you',
                 'herself', 'has', 'just', 'where', 'too', 'only', 'myself', 'which', 'those', 'i', 'after', 'few',
                 'whom', 't', 'being', 'if', 'theirs', 'my', 'against', 'a', 'by', 'doing', 'it', 'how', 'further',
                 'was', 'here', 'than'}

    # common sense for expanding resource-id
    EXPAND = {
        'EditText': {'et': ['edit', 'text']},
        'ImageButton': {'bt': ['button'], 'btn': ['button'], 'fab': ['floating', 'action', 'button']},
        'Button': {'bt': ['button'], 'btn': ['button']},
        'TextView': {'tv': ['text', 'view']}
    }

    # common sense for merging resource-id
    MERGE = [
        ['to', 'do', 'todo'],  # a21-a23-b21, 0-step
        ['sign', 'up', 'signup'],  # Yelp
        ['log', 'in', 'login']  # Yelp
    ]

    TEXT_MERGE = [
        ['Log', 'In', 'Login']  # Yelp
    ]

    SIBLING_TEXT_MERGE = [
        ['Sign', 'in', 'Signin'],  # Yelp
        ['Sign', 'Up', 'Sign_Up'],  # Yelp
    ]

    TEXT_REPLACE = {
        '%': 'percent',  # a54-a55-b51, greedy
        '# of': 'number of',  # a51-a52-b52, greedy
        '# Of': 'number Of'  # a51-a52-b52, greedy
    }

    @staticmethod
    def camel_case_split(identifier):
        # https://stackoverflow.com/questions/29916065/how-to-do-camelcase-split-in-python
        matches = re.finditer('.+?(?:(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|$)', identifier)
        return [m.group(0) for m in matches]

    @staticmethod
    def sanitize(s):
        s = s.strip()
        s = re.sub(r'\s', ' ', s)  # replace [ \t\n\r\f\v] with space
        # convert float with 0 fraction to int, e.g., 15.0 -> 15 (a54-a52-b51)
        try:
            if float(s) and float(s) == int(float(s)):
                s = str(int(float(s)))
        except:
            pass
        for k, v in StrUtil.TEXT_REPLACE.items():
            s = s.replace(k, v)
        s = re.sub(r'[^\w ]', ' ', s)  # replace non [a-zA-Z0-9_], non-space with space
        s = re.sub(r' +', ' ', s)
        return s

    @staticmethod
    def tokenize(s_type, s, use_stopwords=True):
        if not s:
            return []
        if s_type == 'resource-id':
            # e.g., 'acr.browser.lightning:id/search'
            r_id = s.split('/')[-1]
            r_id = StrUtil.sanitize(r_id)
            assert r_id
            tokens = r_id.split('_')
            res = []
            for token in tokens:
                res += [t.lower() for t in StrUtil.camel_case_split(token)]
            res = StrUtil.merge_id(res)
            res = StrUtil.rmv_stopwords(res) if use_stopwords else res
            return res
        elif s_type in ['text', 'content-desc', 'parent_text', 'sibling_text']:
            res = StrUtil.sanitize(s).split()
            res = StrUtil.merge_text(res)
            if s_type == 'sibling_text':
                res = StrUtil.merge_sibling_text(res)
            res = StrUtil.rmv_stopwords(res) if use_stopwords else res
            return res
        elif s_type == 'Activity':
            act_id = s.split('.')[-1]
            act_id = StrUtil.sanitize(act_id)
            assert act_id
            tokens = act_id.split('_')
            res = []
            for token in tokens:
                res += [t.lower() for t in StrUtil.camel_case_split(token)]
            res = StrUtil.rmv_stopwords(res) if use_stopwords else res
            return res
        else:  # never happen
            assert False

    @staticmethod
    def merge_id(word_list):
        for left, right, merged in StrUtil.MERGE:
            if left in word_list and right in word_list and word_list.index(left) == word_list.index(right) - 1:
                word_list = word_list[:word_list.index(left)] + [merged] + word_list[word_list.index(right) + 1:]
        return word_list

    @staticmethod
    def merge_text(word_list):
        """Only replace the beginning"""
        for m in StrUtil.TEXT_MERGE:
            if m[:-1] == word_list:
                return m[-1:]
        return word_list

    @staticmethod
    def merge_sibling_text(word_list):
        """Only replace the beginning"""
        for m in StrUtil.SIBLING_TEXT_MERGE:
            phrase_len = len(m) - 1
            if m[:phrase_len] == word_list[:phrase_len]:
                return [m[-1]] + word_list[phrase_len:]
        return word_list

    @staticmethod
    def rmv_stopwords(tokens):
        # global stopwords
        if len(tokens) > 1:  # remove stopwords only if there are multiple words
            return [t for t in tokens if t not in StrUtil.STOPWORDS]
        else:
            return tokens

    @staticmethod
    def expand_text(w_class, w_attr, w_split_text):
        if w_attr != 'resource-id':
            return w_split_text
        else:
            w_class = w_class.split('.')[-1]
            if w_class in StrUtil.EXPAND:
                new_text = []
                for token in w_split_text:
                    if token in StrUtil.EXPAND[w_class]:
                        new_text += StrUtil.EXPAND[w_class][token]
                    else:
                        new_text.append(token)
                return new_text
            else:
                return w_split_text

    @staticmethod
    def w2v_sent_sim(s_new, s_old):
        # run w2v_service.py first to activate the w2v service
        data = {'s_new': s_new, 's_old': s_old}
        if len(s_new) == 0 or len(s_old) == 0:
            return None
        resp = requests.post(url='http://127.0.0.1:5000/w2v', headers={'Content-Type': 'application/json'}, data=json.dumps(data)).json()
        if 'sent_sim' in resp and resp['sent_sim']:
            return resp['sent_sim']
        else:
            return None

    @staticmethod
    def get_tid(fname):
        return '_'.join(fname.split('.')[:-1])

    @staticmethod
    def get_method(signature):
        # e.g., 'com.example.anycut.CreateShortcutActivity: void onListItemClick(android.widget.ListView,android.view.View,int,long)'
        #       'something.CreateShortcutActivity: Self Loop()'
        assert signature.split()[-1].split('(')[0]
        return signature.split()[-1].split('(')[0]

    @staticmethod
    def get_activity(signature):
        # e.g., 'com.example.anycut.CreateShortcutActivity: void onListItemClick(android.widget.ListView,android.view.View,int,long)'
        #       'something.CreateShortcutActivity: Self Loop()'
        # assert signature.split(':')[0].split('.')[-1]
        # return signature.split(':')[0].split('.')[-1].split('$')[0]
        assert signature.split(':')[0]
        return signature.split(':')[0].split('$')[0]

    @staticmethod
    def is_contain_email(txt):
        return re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', txt)
