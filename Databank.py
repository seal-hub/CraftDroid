from bs4 import BeautifulSoup
import requests
import random
import string


class Databank:
    def __init__(self):
        self.temp_email = ''
        self.password = '1qaz2wsX'
        self.gmail_password = 'mobiletesting'
        self.fname = 'Sealbot'
        self.lname = 'Labfellow'
        self.login_email = 'uci.seal@gmail.com'
        self.email_subject='ICSTSuperCool'
        self.bill_amount = '56.6'
        self.bill_tip = '15'
        self.bill_people = '4'
        self.search_keyword = 'Automated'

    @staticmethod
    def generate_temp_emails():
        for i in range(5):
            uname = ""
            uname += random.choice(string.ascii_lowercase)
            uname += ''.join(random.choice(string.digits) for j in range(6))
            uname += 'se'
            domain = ""
            domain += ''.join(random.choice(string.ascii_lowercase) for j in range(6))
            domain += 'al.net'
            print(uname + '@' + domain)

    def get_temp_email(self, renew=True):
        if not renew and self.temp_email:
            return self.temp_email
        uname = ""
        uname += random.choice(string.ascii_lowercase)
        uname += ''.join(random.choice(string.digits) for j in range(6))
        uname += 'se'
        domain = ""
        domain += ''.join(random.choice(string.ascii_lowercase) for j in range(6))
        domain += '.al.net'
        email = uname + '@' + domain  # e.g., m389997se@thawlq.al.net
        self.temp_email = email
        return self.temp_email

    # def get_temp_email(self, renew=True):
    #     if not renew and self.temp_email:
    #         return self.temp_email
    #     try:
    #         dom = requests.get('https://10minutemail.com/10MinuteMail/index.html').text
    #         soup = BeautifulSoup(dom, 'lxml')
    #         self.temp_email = soup.find('input', 'mail-address-address')['value']
    #         prefix, postfix = self.temp_email.split('@')
    #         prefix = prefix[:-1] + random.choice(string.ascii_letters) + random.choice(string.ascii_letters)
    #         self.temp_email = prefix + '@' + postfix
    #         return self.temp_email
    #     except Exception as e:
    #         print('Error when try to get temp email from 10minutemail.com')
    #         print(e)

    def get_password(self):
        return self.password

    def get_gmail_password(self):
        return self.gmail_password

    def get_fname(self):
        return self.fname

    def get_lname(self):
        return self.lname

    def get_login_email(self):
        return self.login_email

    def get_gmail(self):
        return self.login_email

    def get_email_subject(self):
        return self.email_subject

    def get_bill_amount(self):
        return self.bill_amount

    def get_bill_tip(self):
        return self.bill_tip

    def get_bill_people(self):
        return self.bill_people

    def get_search_keyword(self):
        return self.search_keyword

