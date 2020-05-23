import os
from csv import DictReader
# local import
from Util import Util
from WidgetUtil import WidgetUtil
from const import LOG_FOLDER


class Evaluator:
    def __init__(self, sol_file):
        assert os.path.exists(sol_file), "Invalid config file path"
        self.solution = {}
        with open(sol_file) as f:
            reader = DictReader(f)
            self.solution = [r for r in reader]
        self.res = {'gui': {'tp': 0, 'fp': 0, 'tn': 0, 'fn': 0},
                    'oracle': {'tp': 0, 'fp': 0, 'tn': 0, 'fn': 0}}
        self.finished = 0

    def get_all_config_ids(self, sol_file):
        bid = sol_file.split('-')[-1].split('.')[0]
        config_ids = {}
        for row in self.solution:
            aid_from, aid_to = row['aid_from'], row['aid_to']
            if aid_from not in config_ids:
                config_ids[aid_from] = set()
            config_ids[aid_from].add(aid_to)
        res = []
        for k, v_set in config_ids.items():
            for v_ele in v_set:
                res.append('-'.join([k, v_ele, bid]))
        return res

    def evaluate(self, config_id):
        # print(config_id)
        events_from = Util.load_events(config_id, 'base_from')
        events_to = Util.load_events(config_id, 'base_to')
        events_gen = Util.load_events(config_id, 'generated')
        aid_from = config_id.split('-')[0]
        aid_to = config_id.split('-')[1]
        ans = {}
        for row in self.solution:
            if row['aid_from'] == aid_from and row['aid_to'] == aid_to:
                ans[int(row['step_from'])] = int(row['step_to'])
        idx_gen = 0
        events_pred = []
        for idx_from, src_event in enumerate(events_from):
            # if ans[idx_from] == 7:
            #     print('gg')
            if idx_gen == len(events_gen):
                break
            while events_gen[idx_gen]['event_type'] == 'stepping':
                events_pred.append(events_gen[idx_gen])
                idx_gen += 1
            events_pred.append(events_gen[idx_gen])
            event_ans = events_to[ans[idx_from]] if ans[idx_from] > -1 \
                else {'class': 'EMPTY_EVENT', 'event_type': src_event['event_type']}
            self.judge(events_pred, event_ans, src_event['event_type'])
            events_pred = []
            idx_gen += 1
        if WidgetUtil.is_equal(events_gen[-1], events_to[-1], ignore_activity=True):
            # print('finished:', config_id)
            self.finished += 1
        # else:
        #     print('unfinished:', config_id)

    def judge(self, es_pred, e_ans, event_type):
        # calibrate unimportant text for judge
        for e in es_pred:
            if 'resource-id' in e and e['resource-id'].endswith('folder_name'):
                if e['text'] in ['Inbox ' + str(i) for i in range(1, 21)]:
                    e['text'] = 'Inbox'

        if event_type not in ['gui', 'oracle']:
            return
        ignore_activity = False
        if 'action' in e_ans:
            if e_ans['action'][0] == 'wait_until_text_presence':
                ignore_activity = True
            if e_ans['content-desc'] == 'Navigate up':
                if e_ans['action'][0] == 'wait_until_element_presence' or e_ans['action'][0] == 'click':
                    ignore_activity = True
        cat = None
        if e_ans['class'] == 'EMPTY_EVENT':
            if all([e['class'] == 'EMPTY_EVENT' for e in es_pred]):
                cat = 'tn'
            else:
                cat = 'fp'
                # if event_type == 'oracle':
                #     print(e_ans)
                #     print(es_pred)
        elif e_ans['class'] != 'EMPTY_EVENT':
            if all([e['class'] == 'EMPTY_EVENT' for e in es_pred]):
                cat = 'fn'
            else:
                if any([WidgetUtil.is_equal(e, e_ans, ignore_activity) for e in es_pred]):
                    cat = 'tp'
                    # if event_type == 'gui':
                    #     print(es_pred)
                    #     print(e_ans)
                else:
                    # if event_type == 'gui':
                    #     print(e_ans)
                    #     print(es_pred)
                    #     print('--')
                    # if event_type == 'oracle':
                    #     print(e_ans)
                    #     print(es_pred)
                    cat = 'fp'
        assert cat
        self.res[event_type][cat] += 1

    def output_res(self):
        label = ['tp', 'tn', 'fp', 'fn']
        print(label)
        for k, v in self.res.items():
            print(k)
            res = [v[lbl] for lbl in label]
            print(res)
            print([n/sum(res) for n in res])
            print(f'Precision: {res[0] / (res[0] + res[2])}. '
                  f'Recall: {res[0] / (res[0] + res[3])}')


if __name__ == '__main__':
    total = {
        'gui': {'tp': 0, 'fp': 0, 'tn': 0, 'fn': 0},
        'oracle': {'tp': 0, 'fp': 0, 'tn': 0, 'fn': 0}
    }

    solutions = [
        'solution/a1-b11.csv',
        'solution/a1-b12.csv',
        'solution/a2-b21.csv',
        'solution/a2-b22.csv',
        'solution/a3-b31.csv',
        'solution/a3-b32.csv',
        'solution/a4-b41.csv',
        'solution/a4-b42.csv',
        'solution/a5-b51.csv',
        'solution/a5-b52.csv',
    ]
    # solutions = [
    #     'solution/a3-b31.csv',
    # ]
    for sol in solutions:
        evaluator = Evaluator(sol)
        cids = evaluator.get_all_config_ids(sol)
        # cids = ["a35-a33-b31"]
        for cid in cids:
            # print(cid)
            # if cid in ["a31-a35-b32"]:
            #     continue
            evaluator.evaluate(cid)
        # print(evaluator.res)
        evaluator.output_res()
        print(f'Finished: {evaluator.finished}/{len(cids)}')
        for event_type in ['gui', 'oracle']:
            for res in ['tp', 'tn', 'fp', 'fn']:
                total[event_type][res] += evaluator.res[event_type][res]

    print('\n*** Total *** ')
    print(total)
    for event_type in ['gui', 'oracle']:
        print(event_type.upper())
        print('Precision:', total[event_type]["tp"] / (total[event_type]["tp"] + total[event_type]["fp"]))
        print('Recall:', total[event_type]["tp"] / (total[event_type]["tp"] + total[event_type]["fn"]))
    # tp = total['gui']["tp"] + total['oracle']["tp"]
    # fp = total['gui']["fp"] + total['oracle']["fp"]
    # tn = total['gui']["tn"] + total['oracle']["tn"]
    # fn = total['gui']["fn"] + total['oracle']["fn"]
    # all = tp+fp+tn+fn
    # print(tp/all, tn/all, fp/all, fn/all)
    # print(tp/(tp+fp), tp/(tp+fn))

