import os

import lxml.etree
from bs4 import BeautifulSoup
from lxml.etree import tostring
import csv


class ResourceParser:

    WIDGET_TYPES_FOR_LAYOUT = ['TextView', 'EditText', 'Button', 'ImageButton',
                               'android.support.design.widget.FloatingActionButton']#,
                               # 'CheckBox', 'Switch', 'RadioButton']
    CLASS_PREFIX = 'android.widget.'  # to accommodate the class name reported by UI Automator

    def __init__(self, apk_folder):
        if os.path.exists(apk_folder):
            self.apk_folder = apk_folder
            self.pkg = self.extract_pkg()
            self.wName_to_oId, self.oId_to_wName = self.extract_widget_ids()
            self.sName_to_info = self.extract_strings()  # sName -> (text, oId)
            self.lName_to_oId, self.oId_to_lName = self.extract_layout_ids()
            self.oId_to_activity = self.extract_activity_for_constants()
            self.widgets = self.extract_widgets_from_layout()
        else:
            self.wName_to_oId, self.oId_to_wName = {}, {}
            self.sName_to_info = {}
            self.lName_to_oId, self.oId_to_lName = {}, {}
            self.oId_to_activity = {}
            self.widgets = []

    def extract_pkg(self):
        e = lxml.etree.parse(os.path.join(self.apk_folder, 'AndroidManifest.xml'))
        pkg = e.xpath('/manifest')[0].attrib['package']
        assert pkg
        return pkg

    def extract_widget_ids(self):
        wName_to_oId, oId_to_wName = {}, {}
        e = lxml.etree.parse(os.path.join(self.apk_folder, 'res/values/public.xml'))
        for node in e.xpath('//resources/public[@type="id"]'):
            if 'name' in node.attrib and 'id' in node.attrib:
                wName = node.attrib['name']
                oId = str(int(node.attrib['id'], 16))
                assert oId not in oId_to_wName
                oId_to_wName[oId] = wName
                assert wName not in wName_to_oId
                wName_to_oId[wName] = oId
        return wName_to_oId, oId_to_wName

    def extract_strings(self):
        sName_to_text = {}
        # e.g., <string name="character_counter_pattern">%1$d / %2$d</string>
        #       <item type="string" name="mdtp_ampm_circle_radius_multiplier">0.22</item>
        e = lxml.etree.parse(os.path.join(self.apk_folder, 'res/values/strings.xml'))
        for node in e.xpath('//resources/string'):
            if 'name' in node.attrib:
                soup = BeautifulSoup(tostring(node), 'lxml')
                sName = node.attrib['name']
                assert sName not in sName_to_text
                if soup.text.strip():
                    sName_to_text[sName] = soup.text.strip()
                else:
                    sName_to_text[sName] = ""
        for node in e.xpath('//resources/item'):
            if 'name' in node.attrib and 'type' in node.attrib and node.attrib['type'] == 'string':
                soup = BeautifulSoup(tostring(node), 'lxml')
                if soup.text.strip():
                    sName = node.attrib['name']
                    assert sName not in sName_to_text
                    sName_to_text[sName] = soup.text.strip()
        sName_to_oId = {}
        e = lxml.etree.parse(os.path.join(self.apk_folder, 'res/values/public.xml'))
        for node in e.xpath('//resources/public[@type="string"]'):
            if 'name' in node.attrib and 'id' in node.attrib:
                sName = node.attrib['name']
                oId = str(int(node.attrib['id'], 16))
                assert sName not in sName_to_oId
                sName_to_oId[sName] = oId
        invalid_keys = set(sName_to_oId.keys()).difference(set(sName_to_text.keys()))  # strings without text
        for k in invalid_keys:
            sName_to_oId.pop(k)
        assert set(sName_to_oId.keys()) == set(sName_to_text.keys())
        sName_to_info = {}
        for sName, text in sName_to_text.items():
            sName_to_info[sName] = (text, sName_to_oId[sName])
        return sName_to_info

    def extract_layout_ids(self):
        lName_to_oId, oId_to_lName = {}, {}
        e = lxml.etree.parse(os.path.join(self.apk_folder, 'res/values/public.xml'))
        for node in e.xpath('//resources/public[@type="layout"]'):
            if 'name' in node.attrib and 'id' in node.attrib:
                lName = node.attrib['name']
                oId = str(int(node.attrib['id'], 16))
                assert oId not in oId_to_lName
                oId_to_lName[oId] = lName
                assert lName not in lName_to_oId
                lName_to_oId[lName] = oId
        return lName_to_oId, oId_to_lName

    def extract_activity_for_constants(self):
        oId_to_act = {}
        with open(os.path.join(self.apk_folder, 'atm/constantInfo.csv')) as f:
            # fields: constantId, packageIn, methodIn, methodRefClass, methodRef, codeUnit,
            # (varName, varClass, varRefClass)
            reader = csv.DictReader(f)
            for row in reader:
                oId = row['constantId']
                if row['packageIn'].startswith(self.pkg) and (oId in self.oId_to_wName or oId in self.oId_to_lName):
                    oId_to_act[oId] = {'package': self.pkg,
                                       'activity': row['packageIn'].replace(self.pkg, ''),
                                       'method': row['methodIn']}
        return oId_to_act

    def extract_widgets_from_layout(self):
        parent_layout = {}
        layout_folder = os.path.join(self.apk_folder, 'res/layout')
        layout_xmls = [f for f in os.listdir(layout_folder)
                       if os.path.isfile(os.path.join(layout_folder, f)) and f.endswith('.xml')]

        # first pass to get layout hierarchy
        for xml_file in layout_xmls:
            current_layout = xml_file.split('.')[0]
            e = lxml.etree.parse(os.path.join(layout_folder, xml_file))
            for node in e.xpath('//include'):  # e.g., <include layout="@layout/content_main" />
                child_layout = self.decode(node.attrib['layout'])
                parent_layout[child_layout] = current_layout

        # second pass to get widgets from a layout
        # android.widget.ImageButton

        attrs = ['id', 'text', 'contentDescription', 'hint']
        attrs_ui = ['resource-id', 'text', 'content-desc', 'text']  # the attributes interpreted by UI Automator
        widgets = []
        for xml_file in layout_xmls:
            # print(xml_file)
            current_layout = xml_file.split('.')[0]
            e = lxml.etree.parse(os.path.join(layout_folder, xml_file))
            for w_type in ResourceParser.WIDGET_TYPES_FOR_LAYOUT:
                for node in e.xpath('//' + w_type):
                    d = {}
                    for k, v in node.attrib.items():
                        # attrib: {http://schemas.android.com/apk/res/android}id, @id/ok
                        for a in attrs:
                            k = k.split('}')[1] if k.startswith('{') else k
                            if k == a:
                                a_ui = attrs_ui[attrs.index(a)]
                                if a_ui in d:
                                    d[a_ui] += self.decode(v)
                                else:
                                    d[a_ui] = self.decode(v)
                                # d[a] = v
                    if d:
                        d['class'] = w_type
                        # FloatingActionButton will appear as ImageButton when interpreted by UI Automator
                        if d['class'] == 'android.support.design.widget.FloatingActionButton':
                            d['class'] = 'ImageButton'
                        d['class'] = ResourceParser.CLASS_PREFIX + d['class']
                        if 'resource-id' in d:
                            d['oId'] = self.get_oId_from_wName(d['resource-id'])
                        else:
                            d['oId'] = ""
                        mother_layout = current_layout
                        while mother_layout in parent_layout:
                            mother_layout = parent_layout[mother_layout]
                        d['layout_name'] = mother_layout
                        d['layout_oId'] = self.get_oId_from_lName(mother_layout)
                        d['package'], d['activity'], d['method'] = self.match_act_info_for_oId(d['oId'], d['layout_oId'])
                        for a in attrs_ui:
                            if a not in d:
                                d[a] = ""
                        # if d['name'] or d['oId']:
                        widgets.append(d)
                        # print(d)
        return widgets

    def decode(self, value):
        if not value.startswith('@'):
            return value
        if value.startswith('@id'):  # e.g,. @id/newShortcut
            return value.split('/')[-1]
        if value.startswith('@layout'):  # e.g,. @layout/content_main
            return value.split('/')[-1]
        if value.startswith('@string'):
            sName = value.split('/')[-1]
            # print(value, sName, self.sName_to_info.keys())
            if sName in self.sName_to_info:
                return self.sName_to_info[sName][0]
            else:
                return sName
        if value.startswith('@android:string'):  # e.g., @android:string/cancel
            return value.split('/')[-1]
        if value.startswith('@android:id'):  # e.g., @android:id/button3
            return value.split('/')[-1]
        return value

    def match_act_info_for_oId(self, widget_id, layout_id):
        act_from_w, act_from_l = self.get_activity_from_oId(widget_id), self.get_activity_from_oId(layout_id)
        if act_from_w and act_from_l:
            # print(widget_id, layout_id)
            # print(act_from_w['activity'].split('$')[0])
            # print(act_from_l['activity'].split('$')[0])
            if act_from_w['activity'].split('$')[0] != act_from_l['activity'].split('$')[0]:
                if 'Activity' in act_from_w['activity'].split('$')[0] or 'activity' in act_from_w['activity'].split('$')[0]:
                    return act_from_w['package'], act_from_w['activity'], act_from_w['method']
                elif 'Activity' in act_from_l['activity'].split('$')[0] or 'activity' in act_from_l['activity'].split('$')[0]:
                    return act_from_l['package'], act_from_l['activity'], act_from_l['method']
                else:
                    assert False
            return act_from_w['package'], act_from_w['activity'], act_from_w['method']
        elif act_from_w or act_from_l:
            if act_from_w:
                return act_from_w['package'],act_from_w['activity'], act_from_w['method']
            else:
                return act_from_l['package'],act_from_l['activity'], act_from_l['method']
        else:
            return "", "", ""

    # def extract_activities(self):
    #     e = lxml.etree.parse(os.path.join(self.apk_folder, 'AndroidManifest.xml'))
    #     pkg = e.xpath('/manifest')[0].attrib['package']
    #     acts = []
    #     for node in e.xpath('//activity'):
    #         # print(node.attrib)
    #         # e.g., node.attrib: {'{http://schemas.android.com/apk/res/android}name': '.CreateShortcutActivity'}
    #         attrs = {}
    #         for k, v in node.attrib.items():
    #             filtered_k = k.split('}')[1]
    #             if filtered_k == 'name' and v.startswith('.'):
    #                 v = pkg + v
    #             attrs[filtered_k] = v
    #             # attrs[filtered_k] = decode(v)
    #         if 'name' in attrs:
    #             acts.append(attrs)
    #     return pkg, acts

    def get_widgets(self):
        return self.widgets

    def get_oId_from_wName(self, wName):
        if wName in self.wName_to_oId:
            return self.wName_to_oId[wName]
        else:
            return None

    def get_wName_from_oId(self, oId):
        if oId in self.oId_to_wName:
            return self.oId_to_wName[oId]
        else:
            return None

    def get_lName_from_oId(self, oId):
        if oId in self.oId_to_lName:
            return self.oId_to_lName[oId]
        else:
            return None

    def get_oId_from_lName(self, lName):
        if lName in self.lName_to_oId:
            return self.lName_to_oId[lName]
        else:
            return None

    def get_activity_from_oId(self, oId):
        if oId in self.oId_to_activity:
            return self.oId_to_activity[oId]
        else:
            return None


if __name__ == '__main__':
    from const import SA_INFO_FOLDER
    apk_name = 'a43'
    apk_folder = os.path.join(SA_INFO_FOLDER, apk_name)
    extractor = ResourceParser(apk_folder)
    # print(len(extractor.oId_to_wName.keys()))
    # print(len(extractor.oId_to_lName.keys()))
    # print(extractor.get_wName_from_oId('2131296316'))
    # print(extractor.get_wName_from_oId('2131296521'))
    # print(extractor.get_lName_from_oId('2131427361'))
    # print(extractor.get_oId_from_wName('fab_new_task'))
    print(len(extractor.wName_to_oId), len(extractor.widgets))
    print(len([w for w in extractor.widgets if w['activity'] and w['method']]))
    for w in extractor.get_widgets():
        if w['activity'] and w['method']:
            print(w)
