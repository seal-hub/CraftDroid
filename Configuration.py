import os
from csv import DictReader

# local import
from const import TEST_REPO, CONFIG_FILE


class Configuration:
    def __init__(self, config_id):
        # config_id: aid_from-aid_to-scenario_id, e.g., a41a-a42a-b41
        configs = Configuration.load()
        self.id = ''
        for c in configs:
            if c['id'] == config_id:
                self.id = config_id
                self.no_reset = True if c['reset_data'] == 'False' else False
                self.use_stopwords = False if c['use_stopwords'] == 'False' else True
                self.expand_btn_to_text = False if c['expand_btn_to_text'] == 'False' else True
                self.cross_check = False if c['cross_check'] == 'False' else True
                self.pkg_from, self.act_from, self.pkg_to, self.act_to = Configuration.get_pkg_info(config_id)
        assert self.id, 'Invalid config_id'

    @staticmethod
    def load():
        assert os.path.exists(CONFIG_FILE), "Invalid config file path"
        with open(CONFIG_FILE, newline='') as cf:
            reader = DictReader(cf)
            configs = [row for row in reader]
        return configs

    @staticmethod
    def get_pkg_info(config_id):
        # e.g., a41a-a42a-b41
        folder = config_id[:2]  # e.g., a4
        fpath = os.path.join(TEST_REPO, folder, folder + '.config')
        assert os.path.exists(fpath), 'Invalid app config path'
        pkg_from, act_from, pkg_to, act_to = '', '', '', ''
        with open(fpath, newline='') as cf:
            reader = DictReader(cf)  # aid,package,activity
            for row in reader:
                if row['aid'] == config_id.split('-')[0]:
                    pkg_from, act_from = row['package'], row['activity']
                elif row['aid'] == config_id.split('-')[1]:
                    pkg_to, act_to = row['package'], row['activity']
        assert pkg_from and pkg_to, 'Invalid config_id'
        return pkg_from, act_from, pkg_to, act_to
