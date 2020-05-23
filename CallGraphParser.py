import networkx as nx
import pydot
import os
import re
from collections import defaultdict

# local import
from StrUtil import StrUtil
from WidgetUtil import WidgetUtil


class CallGraphParser:
    def __init__(self, apk_folder):
        self.apk_folder = apk_folder
        self.G = self.get_graph_from_dot_file()  # a MultiDiGraph
        # self.act_to_nodes = #self.group_nodes()
        # self.act_to_onCreate_node = self.
        self.act_to_nodes = defaultdict(list)
        self.act_to_onCreate_node = {}
        self.onCreate_param = {"android.os.Bundle"}
        self.group_nodes()
        self.self_loops = defaultdict(list)
        # for k, v in self.act_to_onCreate_node.items():
        #     print(k, v)
        # print(self.onCreate_param)
        # self.w_to_edges = self.extract_gui_edges()
        # self.layout_to_widgets = defaultdict(list)

    def get_graph_from_dot_file(self):
        if os.path.exists(os.path.join(self.apk_folder, 'atm/atm.gv')):
            graphs = pydot.graph_from_dot_file(os.path.join(self.apk_folder, 'atm/atm.gv'))
            (g2,) = graphs
            # print(g2)
            G = nx.nx_pydot.from_pydot(g2)
            # remove edges with label "GUI (NULL)"
            G2 = nx.MultiDiGraph()
            for n in G.nodes:
                G2.add_node(n)
            for e in G.edges:
                lbl = G.edges[e]['label']
                if lbl != '"GUI (NULL)"':
                    G2.add_edge(e[0], e[1], label=lbl)
            return G2
        else:
            return nx.MultiDiGraph()

    def group_nodes(self):
        for node in self.G.nodes:
            act = StrUtil.get_activity(node)
            self.act_to_nodes[act].append(node)
            # e.g., org.secuso.privacyfriendlytodolist.view.SplashActivity: void onCreate(android.os.Bundle)
            if ': void onCreate(' in node:
                assert node not in self.act_to_onCreate_node
                self.act_to_onCreate_node[act] = node
                param = node.split('(')[1].split(')')[0]
                self.onCreate_param.add(param)
        # print(act_to_nodes['org.secuso.privacyfriendlytodolist.view.MainActivity'])
        for k in self.act_to_nodes.keys():
            # sort activities by name and method length in ascending order
            # e.g., prefer MainActivity than MainActivity$1; prefer onStart() than startListDialog()
            self.act_to_nodes[k] = sorted(self.act_to_nodes[k],
                                          key=lambda x: (x.split(':')[0], len(StrUtil.get_method(x))))

    def get_paths_between_activities(self, act_from, act_to, consider_naf_only_widget=False):
        all_paths = {}
        nodes_from, nodes_to = self.act_to_nodes[act_from], self.act_to_nodes[act_to]
        for n_from in nodes_from:
            for n_to in nodes_to:
                paths = self.get_paths_between_nodes(n_from, n_to, consider_naf_only_widget)
                for path in paths:
                    key = ''.join(path)
                    if key not in all_paths:
                        all_paths[key] = path
        return list(all_paths.values())

    def get_paths_between_nodes(self, n_from, n_to, consider_naf_only_widget=False):
        """For now, only return one path for n_from -> n_to"""
        gui_paths = {}
        if n_from != n_to:
            for hops in nx.all_simple_paths(self.G, source=n_from, target=n_to):
                # print(hops)
                gui_path = []
                for i in range(len(hops) - 1):  # try to find a GUI action for each pair of hops
                    u, v = hops[i], hops[i + 1]
                    for j in range(self.G.number_of_edges(u, v)):
                        e_attrs = self.G.edges[(u, v, j)]
                        gui_event = None
                        m = re.search(r"GUI \((.+)\)", e_attrs['label'])
                        if m and m.group(1) != 'NULL':  # info from static analysis
                                                        # e.g., '"GUI (newShortcut)"'; '"GUI (2131296593)"'
                            gui_event = m.group(1) + ' (' + StrUtil.get_method(v) + ')'
                        elif e_attrs['label'].startswith('D@'):  # info from dynamic exploration
                            # e.g, D@class=android.widget.TextView&content-desc=&naf=&resource-id=create&text=Create (onClick)
                            gui_event = e_attrs['label']
                        if gui_event:
                            gui_path += [StrUtil.get_activity(u), gui_event]
                            break
                # gui_path.append(StrUtil.get_activity(hops[-1]))
                gui_path.append(StrUtil.get_activity(n_to))
                key = ''.join(gui_path)
                if key not in gui_paths and len(gui_path) > 2:
                    gui_paths[key] = gui_path
                    # add one more step at the end if there a self-loop
                    for lbl in self.self_loops.get(n_to, []):  # to repeat at the last activity
                        gui_path_with_a_loop = [h for h in gui_path]
                        if lbl != gui_path_with_a_loop[-2]:  # not to repeat the same GUI event again
                            gui_path_with_a_loop.insert(-1, lbl)
                            key = ''.join(gui_path_with_a_loop)
                            if key not in gui_paths:
                                gui_paths[key] = gui_path_with_a_loop
                    # to repeat at the 2nd to last activity, a31-a35-b31
                    if StrUtil.get_activity(gui_path[-1]) != StrUtil.get_activity(gui_path[-3]):
                        second_to_last = gui_path[-3]
                        nodes = self.act_to_nodes[second_to_last]
                        for node in nodes:
                            for lbl in self.self_loops.get(node, []):
                                gui_path_with_a_loop = [h for h in gui_path]
                                if lbl != gui_path_with_a_loop[-2]:  # not to repeat the same GUI event again
                                    gui_path_with_a_loop.insert(-2, lbl)
                                    key = ''.join(gui_path_with_a_loop)
                                    if key not in gui_paths:
                                        gui_paths[key] = gui_path_with_a_loop
        else:  # n_from == n_to
            for lbl in self.self_loops.get(n_from, []):
                gui_path = [StrUtil.get_activity(n_from), lbl, StrUtil.get_activity(n_from)]
                key = ''.join(gui_path)
                if key not in gui_paths:
                    gui_paths[key] = gui_path
        if not consider_naf_only_widget:
            CallGraphParser.remove_paths_with_naf_only_widgets(gui_paths)
        return list(gui_paths.values())

    def add_edge(self, act_from, act_to, w_stepping):
        """add a dynamically found edge into G"""
        # nx automatically takes care of non-existing / duplicated node issue when adding an edge
        # every node is unique in a graph by its name
        if act_from not in self.act_to_onCreate_node:
            self.act_to_onCreate_node[act_from] = act_from + ': void onCreate(' + list(self.onCreate_param)[0] + ')'
        if act_to not in self.act_to_onCreate_node:
            self.act_to_onCreate_node[act_to] = act_to + ': void onCreate(' + list(self.onCreate_param)[0] + ')'
        act_from = self.act_to_onCreate_node[act_from]
        act_to = self.act_to_onCreate_node[act_to]
        attrs = set(WidgetUtil.FEATURE_KEYS).difference({'clickable', 'password'})
        values = [w_stepping[a] for a in attrs]
        lbl_stepping = '&'.join([a + '=' + v for a, v in zip(attrs, values)])
        action = ' (onLongClick)' if w_stepping['action'][0] == 'long_press' else ' (onClick)'
        lbl_stepping = 'D@' + lbl_stepping + action
        if act_from != act_to:
            is_edge_existed = False
            for i in range(self.G.number_of_edges(act_from, act_to)):
                if lbl_stepping == self.G.edges[(act_from, act_to, i)]['label']:
                    is_edge_existed = True
                    break
            if not is_edge_existed:
                print(f'Adding edge: from {act_from} to {act_to}\nlabel is: {lbl_stepping}')
                self.G.add_edge(act_from, act_to, label=lbl_stepping)
                self.update_act_to_nodes(act_from)
                self.update_act_to_nodes(act_to)
        else:
            if lbl_stepping not in self.self_loops[act_from]:
                print(f'Adding self-loop: {act_from}, label: {lbl_stepping}')
                self.self_loops[act_from].append(lbl_stepping)
                self.G.add_edge(act_from, act_from, label=lbl_stepping)
                self.update_act_to_nodes(act_from)

    def update_act_to_nodes(self, node):
        act = StrUtil.get_activity(node)
        if act not in self.act_to_nodes:
            self.act_to_nodes[act].append(node)
        else:
            if node not in self.act_to_nodes[act]:
                self.act_to_nodes[act].insert(0, node)

    @classmethod
    def remove_paths_with_naf_only_widgets(cls, gui_paths):
        # e.g., a gui_path = ['com.rainbowshops.activity.ProfileActivity',
        #                     'D@text=Log In&class=android.widget.Button&content-desc=&resource-id=button_log_in&naf= (onClick)',
        #                     'D@text=&class=android.widget.ImageButton&content-desc=&resource-id=&naf=true (onClick)',
        #                     'com.rainbowshops.activity.LoginAndSignUpActivity']
        discarded_keys = []
        for k, gpath in gui_paths.items():
            for hop in gpath:
                if CallGraphParser.is_naf_only_widget(hop):
                    discarded_keys.append(k)
                    break
        for k in discarded_keys:
            gui_paths.pop(k, None)

    @classmethod
    def is_naf_only_widget(cls, hop):
        # e.g., 'D@text=&class=android.widget.ImageButton&content-desc=&resource-id=&naf=true (onClick)'
        if not hop.startswith('D@'):
            return False
        hop = ' '.join(hop.split()[:-1])
        kv_pairs = hop[2:].split('&')
        kv = [kvp.split('=') for kvp in kv_pairs]
        # e.g., [['text', 'Art '], [' Collectibles'], ['class', 'android.widget.TextView']]
        curated_kv = []
        for pairs in kv:
            if len(pairs) == 2:
                curated_kv.append(pairs)
            elif len(pairs) == 1:
                curated_kv[-1][1] += '&' + pairs[0]
            else:
                assert False
        criteria = {k: v for k, v in curated_kv}
        if all([v for k, v in criteria.items() if k in ['class', 'naf']]) \
                and not any([v for k, v in criteria.items() if k not in ['class', 'naf']]):
            return True
        return False


if __name__ == '__main__':
    # G = nx.MultiDiGraph()
    # G.add_node("a1")
    # G.add_node("a2")
    # G.add_edge("a1", "a2", label="1")
    # G.add_edge("a1", "a2", label="2")
    # G.add_edge("a1", "a1", label="4")
    # G.add_edge("a1", "a1", label="5")
    # G.add_node("a1")
    # G.add_edge("a8", "a8", label="8")
    # print([p for p in nx.all_simple_paths(G, "a1", "a2")])
    # print(G.number_of_edges("a1", "a9"))
    # print(G.nodes)
    # print(G.edges)
    # print(G.number_of_edges('a1', 'a1'))

    # G = nx.complete_graph(4)
    # print(G.edges)
    # for path in nx.all_simple_paths(G, source=0, target=3):
    #     print(path)

    input()
    apk_name = 'a43'
    apk_folder = os.path.join('sa_info', apk_name)
    cgp = CallGraphParser(apk_folder)
    print(len(cgp.G.nodes), cgp.G.nodes)
    print(len(cgp.G.edges), cgp.G.edges)
    # for n1 in cgp.G.nodes:
    #     for n2 in cgp.G.nodes:
    #         for i in range(cgp.G.number_of_edges(n1, n2)):
    #             print(n1, n2, i, cgp.G.edges[(n1, n2, i)]['label'])
    # paths = cgp.get_paths_between_activities(
    #     'com.zaidisoft.teninone.Calculator',
    #     'com.zaidisoft.teninone.Calculator'
    # )
    # for p in paths:
    #     print(p)
    # for k, v in cgp.act_to_nodes.items():
    #     if 'something.MainActivity: Self Loop()' in v:
    #         print(k)