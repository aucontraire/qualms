# -*- coding: utf-8 -*-
import os
import csv
import sys
import cgi
import re
import datetime
import ustimezone
from collections import Counter, defaultdict
import json
import urllib
import urllib2
from lxml import objectify # parses XML from Qualtrics
import webapp2 # GAE web framework
import jinja2 # templating
from google.appengine.ext import db, deferred # sets up a data model for the GAE Datastore
from google.appengine.api import users, taskqueue


# enables jinja templates for html pages
jinja_environment = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))


def get_templ_vals():
    ''' URLs to pages '''
    template_values = {       
        'url_linktext': 'Logout',
        
        'urla': '/',
        'url_admin': '',
    
        'url_access' : '/addqualaccess',
        'url_access_text' : 'Access',
        
        'url_schedule' : '/addschedule',
        'url_schedule_text' : 'Schedule',
        
        'url_settings' : '/addsettings',
        'url_settings_text' : 'Settings',
        
        'url_followups' : '/addmessageids',
        'url_followups_text' : 'Follow-ups',
        
        'url_sendemail' : '/sendemail',
        'url_sendemail_text' : 'Send email',
        
        'url_download' : '/fucheckup',
        'url_download_text' : 'Download',
    }
    
    return template_values


tformats = '%Y-%m-%d'  # pattern that matches formatting fordate only (formatted: 2013-01-01)
tformatl = '%Y-%m-%d %H:%M:%S'  # pattern that matches formatting for datetime  (formatted: 2013-01-01 23:00:00)
tformatalt = '%m/%d/%Y %I:%M %p' # (10/29/2015 12:00 AM) 

def timeStamp(now):
    """ Formats current datetime to '%Y-%m-%d %H:%M:%S' (2013-02-08 16:39:00)  """
    # date
    d = now.date() # extracts the date from the current datetime
    year = d.year # gets the year
    month = d.month # gets the month
    day = d.day # gets the day of the month
    
    # time
    t = now.time() # extracts the time from the current datetime
    hour = t.hour
    minute = t.minute
    second = t.second
    today_datetime = datetime.datetime(year, month, day, hour, minute, second)
    return today_datetime

def qualtricsCall(data):
    """ Standard parameters common to all Qualtrics REST API calls """
    
    q = qualtricsAccessInfo.all()
    q.order('-date_created')
    
    access_data = {}
    access_data['User'] = q[0].user_name
    access_data['Token'] = q[0].api_token
    access_data['LibraryID'] = q[0].library_id
    access_data['PanelID'] = q[0].panel_id

    data['Format'] = 'XML'
    data['Version'] = '2.5'
    
    return access_data


class qualtricsAccessInfo(db.Model):
    """ Models a list of user-related info to access Qualtrics API """
    created_by = db.UserProperty(auto_current_user_add=True)
    date_created = db.DateTimeProperty(auto_now_add=True)
    last_modified_by = db.UserProperty(auto_current_user=True) # Google account which made changes
    last_modified = db.DateTimeProperty(auto_now=True)
    
    user_name = db.StringProperty() # User
    api_token = db.StringProperty() # Token
    library_id = db.StringProperty() # LibraryID, PanelLibraryID, MessageLibraryID
    panel_id = db.StringProperty() # PanelID


def qualtricsAccessInfoByKeyName(user_name):
    user_name = re.sub(r'(#+)', r'', user_name) # removes the problematic # to use in the query
    return qualtricsAccessInfo.get_by_key_name(user_name)


class emailSchedule(db.Model):
    """  Models a list of settings related to project timeline and other parameters """
    created_by = db.UserProperty(auto_current_user_add=True)
    date_created = db.DateTimeProperty(auto_now_add=True)
    last_modified_by = db.UserProperty(auto_current_user=True) # Google account which made changes
    last_modified = db.DateTimeProperty(auto_now=True)
    
    time_zone = db.StringProperty() # Time zone of study
    start_date = db.DateTimeProperty() # Datetime when emails should begin (formatted: 2013-01-01 23:00:00)
    stop_date = db.DateTimeProperty() # Datetime when emails should stop (formatted: 2013-01-01 23:00:00)
    follow_up_num = db.IntegerProperty() # Number of follow-ups
    interval = db.IntegerProperty() # Number of days between each follow-up, this is problematic for multiple messages in a day


def emailScheduleById(schedule_id):
    return emailSchedule.get_by_id(schedule_id)


def is_study_active():
    
    schedule_query = emailSchedule.all()
    time_zone = schedule_query[0].time_zone
    start_date = schedule_query[0].start_date
    stop_date = schedule_query[0].stop_date
    
    if time_zone == 'Eastern':
        zone = datetime.datetime.now(tz=ustimezone.Eastern) # get current Eastern datetime
    elif time_zone == 'Central':
        zone = datetime.datetime.now(tz=ustimezone.Central) # get current Central datetime
    elif time_zone == 'Mountain':
        zone = datetime.datetime.now(tz=ustimezone.Mountain) # get current Mountain datetime
    else:
        zone = datetime.datetime.now(tz=ustimezone.Pacific) # get current Pacific datetime
        
    local_date = datetime.datetime(zone.year, zone.month, zone.day, zone.hour, zone.minute, zone.second)
    
    if local_date >= start_date and local_date <= stop_date:
        study_active = 1
    else:
        study_active = 0
    
    return study_active
        
   
class emailSettings(db.Model):
    """  Models a list of emails settings for follow-up emails """
    created_by = db.UserProperty(auto_current_user_add=True)
    date_created = db.DateTimeProperty(auto_now_add=True)
    last_modified_by = db.UserProperty(auto_current_user=True) # Google account which made changes
    last_modified = db.DateTimeProperty(auto_now=True)
    
    survey_name = db.StringProperty() # NEW (delete? It may not make sense given the custom settings in the message ids table/form)
    survey_id = db.StringProperty() # SurveyID
    from_email = db.EmailProperty() # FromEmail
    from_name = db.StringProperty() # FromName
    subject_txt = db.StringProperty() # Subject


def emailSettingsByKeyName(from_email):
    return emailSettings.get_by_key_name(from_email)


def settingData():
    """  Queries settings table """
    settings_query = emailSettings.all()
    settings_query.order('-date_created')
    
    settings_data = {}
    settings_data['from_email'] = settings_query[0].from_email
    settings_data['from_name'] = settings_query[0].from_name
    
    return settings_data
 
    
class messageIDs(db.Model):
    """ Models a list of follow-ups including message ids and follow-up periods. """
    created_by = db.UserProperty(auto_current_user_add=True)
    date_created = db.DateTimeProperty(auto_now_add=True)
    last_modified_by = db.UserProperty(auto_current_user=True) # Google account which made changes
    last_modified = db.DateTimeProperty(auto_now=True)
    
    fu_period = db.IntegerProperty()
    message_id = db.StringProperty() #MessageID
    survey_id = db.StringProperty() # SurveyID
    subject_txt = db.StringProperty() # Subject
    days_since = db.IntegerProperty()
    
    reminder_number = db.IntegerProperty(default=0)
    reminder_days = db.IntegerProperty()
    reminder_message_id = db.StringProperty()

    
def messageIDByKeyName(message_id):
    return messageIDs.get_by_key_name(message_id)


def messageData(follow_up):
    """  Queries follow-up table """
    
    message_query = messageIDs.all()
    message_query.order('fu_period')
    
    i = follow_up - 1
    survey_id =  message_query[i].survey_id
    subject_txt = message_query[i].subject_txt
    
    return survey_id, subject_txt


class emailJobs(db.Model):
    """ Models a list of email jobs for each participant """
    date_created = db.DateTimeProperty(auto_now_add=True)
    last_modified = db.DateTimeProperty(auto_now=True) # NEW
    recipient_id = db.StringProperty() # RecipientID
    trigger_id = db.StringProperty()  # TriggerResponseID
    test_data = db.IntegerProperty(default=0) # Identifies test data (TESTDATA=1) TODO: Decide whether to change to Boolean
    unsubscribed = db.IntegerProperty() # Subscription status TODO: Decide whether to change to Boolean
    unsubscribe_date = db.DateTimeProperty() # NEW
    start_date_local = db.DateTimeProperty() # STARTDATE datetime (timestamp) in participant's local time zone
    consent_date = db.DateTimeProperty() # CONSENTDATE datetime (timestamp) in UTC
    fu_period = db.IntegerProperty() #Follow-up period 
    fu1 = db.DateTimeProperty() # Follow-up 1 datetime
    fu2 = db.DateTimeProperty()
    fu3 = db.DateTimeProperty()
    fu4 = db.DateTimeProperty()
    fu5 = db.DateTimeProperty()
    fu6 = db.DateTimeProperty()
    fu7 = db.DateTimeProperty()
    fu8 = db.DateTimeProperty()
    fu9 = db.DateTimeProperty()
    fu10 = db.DateTimeProperty()
    fu11 = db.DateTimeProperty()
    fu12 = db.DateTimeProperty()
    fu13 = db.DateTimeProperty()
    fu14 = db.DateTimeProperty()
    fu15 = db.DateTimeProperty()
    fu16 = db.DateTimeProperty()
    fu17 = db.DateTimeProperty()
    fu18 = db.DateTimeProperty()
    fu19 = db.DateTimeProperty()
    fu20 = db.DateTimeProperty()
    fu21 = db.DateTimeProperty()
    fu22 = db.DateTimeProperty()
    fu23 = db.DateTimeProperty()
    fu24 = db.DateTimeProperty()
    fu25 = db.DateTimeProperty()
    fu26 = db.DateTimeProperty()
    fu27 = db.DateTimeProperty()
    fu28 = db.DateTimeProperty()
    fu29 = db.DateTimeProperty()
    fu30 = db.DateTimeProperty()
    
    last_fu_sent = db.DateTimeProperty() # Datetime last follow-up email was sent
    
    fu1_email_sent = db.DateTimeProperty()  # Datetime that follow-up 1 was sent
    fu2_email_sent = db.DateTimeProperty()
    fu3_email_sent = db.DateTimeProperty()
    fu4_email_sent = db.DateTimeProperty()
    fu5_email_sent = db.DateTimeProperty()
    fu6_email_sent = db.DateTimeProperty()
    fu7_email_sent = db.DateTimeProperty()
    fu8_email_sent = db.DateTimeProperty()
    fu9_email_sent = db.DateTimeProperty()
    fu10_email_sent = db.DateTimeProperty()
    fu11_email_sent = db.DateTimeProperty()
    fu12_email_sent = db.DateTimeProperty()
    fu13_email_sent = db.DateTimeProperty()
    fu14_email_sent = db.DateTimeProperty()
    fu15_email_sent = db.DateTimeProperty()
    fu16_email_sent = db.DateTimeProperty()
    fu17_email_sent = db.DateTimeProperty()
    fu18_email_sent = db.DateTimeProperty()
    fu19_email_sent = db.DateTimeProperty()
    fu20_email_sent = db.DateTimeProperty()
    fu21_email_sent = db.DateTimeProperty()
    fu22_email_sent = db.DateTimeProperty()
    fu23_email_sent = db.DateTimeProperty()
    fu24_email_sent = db.DateTimeProperty()
    fu25_email_sent = db.DateTimeProperty()
    fu26_email_sent = db.DateTimeProperty()
    fu27_email_sent = db.DateTimeProperty()
    fu28_email_sent = db.DateTimeProperty()
    fu29_email_sent = db.DateTimeProperty()
    fu30_email_sent = db.DateTimeProperty()

    edited_by = db.StringProperty() # Google account which made changes
    comments = db.StringProperty(multiline=True) #Comments
    
    @classmethod
    def addto_datastore(cls, recipient_id, access_data, follow_up_number, fu_dict, interval):
        """ Class method that adds participant records (entities) to emailJobs table """
        
        email_jobs = cls.get_by_key_name(recipient_id)
        if email_jobs is None:
            email_jobs = cls(key_name=recipient_id)  
                
        email_jobs.recipient_id = recipient_id
        
        getPanelParse(recipient_id, access_data, follow_up_number, fu_dict, interval, email_jobs)
        
        email_jobs.put()
        
    @classmethod
    def update_unsub(cls, recipient_id):
        """ Class method that updates unsubscribed participants """
        email_jobs = cls.get_by_key_name(recipient_id)
        email_jobs.unsubscribed = 1
        now = datetime.datetime.now()
        email_jobs.unsubscribe_date = timeStamp(now)
        
        email_jobs.put()
        
    @classmethod
    def update_fu(cls, recipient_id, fup):
        """ Class method that updates follow-up period """
        email_jobs = cls.get_by_key_name(recipient_id)
        email_jobs.fu_period = fup
        
        email_jobs.put()
    
    @classmethod
    def update_fusent(cls, recipient_id, follow_up, send_date_utc):
        """ Class method that updates fux_email_sent in emailJobs table """
        
        email_jobs = cls.get_by_key_name(recipient_id)
        
        i = str(follow_up)
        follow_up_sent = 'fu' + i + '_email_sent'
        setattr(email_jobs, follow_up_sent, send_date_utc)
           
        email_jobs.last_fu_sent = send_date_utc

        email_jobs.put()
        

def emailJobsByKeyName(recipient_id):  
    return emailJobs.get_by_key_name(recipient_id)

    
class lastRecipientID(db.Model):
    """ Models a list of the last RecipientID from each Qualtrics REST API call to be used as a reference point in the next cron job that adds new participants """
    date_created = db.DateTimeProperty(auto_now_add=True)
    last_recipientid = db.StringProperty() # LastRecipientID - Original panel
    number_downloaded = db.IntegerProperty() # Number of records downloaded from Qualtrics panel


class fusSent(db.Model):
    """ Models a global list of the follow-ups due and follow-ups sent """
    date_created = db.DateTimeProperty(auto_now_add=True)
    last_modified = db.DateTimeProperty(auto_now=True)
    fu_date = db.DateProperty() 
    fus_due = db.IntegerProperty() # The number of follow-up emails due for this date
    fus_sent = db.IntegerProperty()  # The number of follow-up emails sent for this date


def fusSentByKeyName(fu_date):
    return fusSent.get_by_key_name(fu_date)

def ejs_exist():
    ejs = emailJobs.all()
    if ejs.count() == 0:
        return 0
    else:
        return 1  


class MainPage(webapp2.RequestHandler):
    """GAE - Qualtrics main admin page """
    
    def get(self):
        if users.get_current_user():
            template_values = get_templ_vals()
            url = users.create_logout_url(self.request.uri)
            template_values['url'] = url
            template_values['admin'] = 0
            
            if users.is_current_user_admin():
                template_values['download'] = ejs_exist()
                template_values['admin'] = 1
                template_values['urla'] = '_ah/admin/'
                template_values['url_admin'] = 'GAE'
        else:
            template_values = get_templ_vals()
            url = users.create_login_url(self.request.uri)
            template_values['url'] = url
            template_values['url_linktext'] = 'Login'
            
        template = jinja_environment.get_template('index.html')
        self.response.out.write(template.render(template_values))


class addQualtricsAccessInfo(webapp2.RequestHandler):
    """ Adds Qualtrics user-related info to qualtricsAccessInfo table via an html form """
    
    def get(self):
        if users.get_current_user():
            template_values = get_templ_vals()
            url = users.create_logout_url(self.request.uri)
            template_values['url'] = url
            template_values['admin'] = 0
            
            if users.is_current_user_admin():
                template_values['download'] = ejs_exist()  
                qualtrics_access = qualtricsAccessInfo.all()
                template_values['admin'] = 1
                template_values['urla'] = '_ah/admin/'
                template_values['url_admin'] = 'GAE'
                template_values['qualtrics_access'] = qualtrics_access
        else:
            template_values = get_templ_vals()
            url = users.create_login_url(self.request.uri)
            template_values['url'] = url
            template_values['url_linktext'] = 'Login'

        template = jinja_environment.get_template('addqualaccess.html')
        self.response.out.write(template.render(template_values))

    def post(self):     
        template_values = get_templ_vals()
        template_values['download'] = ejs_exist()
        url = users.create_logout_url(self.request.uri)
        template_values['url'] = url
        template_values['admin'] = 1
        template_values['urla'] = '_ah/admin/'
        template_values['url_admin'] = 'GAE'
        qualtrics_access = qualtricsAccessInfo.all()
        template_values['qualtrics_access'] = qualtrics_access
        
        user_name = self.request.get('user_name')
        new_user = re.sub(r'(#+)', r'', user_name)
        qualtrics_cred = qualtricsAccessInfo(key_name=new_user)
        qualtrics_cred.user_name = user_name
        qualtrics_cred.api_token = self.request.get('api_token') 
        qualtrics_cred.library_id = self.request.get('library_id')
        qualtrics_cred.panel_id = self.request.get('panel_id')
        qualtrics_cred.put()
        
        template = jinja_environment.get_template('addqualaccess.html')
        self.response.out.write(template.render(template_values))

        
class editQualtricsAccessInfo(webapp2.RequestHandler):
    """  Edits Qualtrics user-related info in qualtricsAccessInfo table via an html form """
    def get(self):
        user_name = self.request.get('id')
        newpost = qualtricsAccessInfoByKeyName(user_name)
        
        date_created = newpost.date_created
        last_modified = newpost.last_modified 
        last_modified_by = newpost.last_modified_by
        panel_id = newpost.panel_id
        library_id = newpost.library_id 
        api_token = newpost.api_token
        user_key = newpost.key().name()
        user_name = newpost.user_name
        
        if users.get_current_user():
            template_values = get_templ_vals()
            url = users.create_logout_url(self.request.uri)
            template_values['url'] = url
            template_values['admin'] = 0
            
            if users.is_current_user_admin():
                template_values['download'] = ejs_exist()    
                template_values['admin'] = 1
                template_values['urla'] = '_ah/admin/'
                template_values['url_admin'] = 'GAE'
                template_values['user_name'] = user_name
                template_values['user_key'] = user_key
                template_values['panel_id'] = panel_id
                template_values['library_id'] = library_id
                template_values['last_modified_by'] = last_modified_by
                template_values['date_created'] = date_created.strftime('%m/%d/%Y %I:%M %p')
                template_values['last_modified'] = last_modified.strftime('%m/%d/%Y %I:%M %p')
                template_values['api_token'] = api_token
                 
        else:
            template_values = get_templ_vals()
            url = users.create_login_url(self.request.uri)
            template_values['url'] = url
            template_values['url_linktext'] = 'Login'
        
        template = jinja_environment.get_template('editqualaccess.html')
        self.response.out.write(template.render(template_values))
        
    def post(self):
        user_name = self.request.get('id')
        panel_id = self.request.get('panel_id')
        library_id = self.request.get('library_id')
        api_token = self.request.get('api_token')
        
        newpost = qualtricsAccessInfoByKeyName(user_name)
        newpost.panel_id = panel_id
        newpost.library_id = library_id
        newpost.api_token = api_token
        newpost.put()
        
        self.redirect('/addqualaccess')
        

class deleteQualtricsAccessInfo(webapp2.RequestHandler):
    """  Deletes Qualtrics user-related info to qualtricsAccessInfo table via an html form """
    def post(self):
        user_name = self.request.get('id')
        newpost = qualtricsAccessInfoByKeyName(user_name)
        newpost.delete()
        self.redirect('/addqualaccess')


class addEmailSchedule(webapp2.RequestHandler):
    """ Adds project parameters and timeline info to emailSchedule table via an html form """
    def get(self):       
        schedule_query = emailSchedule.all()
        schedule_query.order('date_created')
        
        if users.get_current_user():
            template_values = get_templ_vals()
            url = users.create_logout_url(self.request.uri)
            template_values['url'] = url
            template_values['admin'] = 0
            
            if users.is_current_user_admin():
                template_values['download'] = ejs_exist()    
                template_values['admin'] = 1
                template_values['urla'] = '_ah/admin/'
                template_values['url_admin'] = 'GAE'
                template_values['schedule_query'] = schedule_query
        else:
            template_values = get_templ_vals()
            url = users.create_login_url(self.request.uri)
            template_values['url'] = url
            template_values['url_linktext'] = 'Login'

        template = jinja_environment.get_template('addschedule.html')
        self.response.out.write(template.render(template_values))
        
    def post(self):
        template_values = get_templ_vals()
        url = users.create_logout_url(self.request.uri)
        template_values['url'] = url
        template_values['admin'] = 1
        template_values['urla'] = '_ah/admin/'
        template_values['url_admin'] = 'GAE'
        
        schedule_query = emailSchedule.all()
        schedule_query.order('date_created')
        template_values['schedule_query'] = schedule_query
        
        email_schedule = emailSchedule()
        
        email_schedule.time_zone = str(self.request.get('time_zone'))
        email_schedule.start_date = datetime.datetime.strptime(self.request.get('start_date'), tformatalt)
        email_schedule.stop_date = datetime.datetime.strptime(self.request.get('stop_date'), tformatalt)
        email_schedule.follow_up_num = int(self.request.get('follow_up_num'))
                
        interval = self.request.get('interval')
        if interval == '':
            email_schedule.interval = None
        else:
            email_schedule.interval = int(interval)
        
        email_schedule.put()
        
        template = jinja_environment.get_template('addschedule.html')
        self.response.out.write(template.render(template_values))
    

class editEmailSchedule(webapp2.RequestHandler):
    """  Edits project parameters and timeline info in emailSchedule table via an html form  """
    def get(self):
        key_id = int(self.request.get('id'))
        newpost = emailScheduleById(key_id)
        
        date_created = newpost.date_created
        last_modified = newpost.last_modified 
        last_modified_by = newpost.last_modified_by
        time_zone = newpost.time_zone
        start_date = newpost.start_date
        stop_date = newpost.stop_date
        follow_up_num = newpost.follow_up_num
        interval = newpost.interval
        
        if users.get_current_user():
            template_values = get_templ_vals()
            url = users.create_logout_url(self.request.uri)
            template_values['url'] = url
            template_values['admin'] = 0
            
            if users.is_current_user_admin():
                template_values['download'] = ejs_exist()                  
                template_values['admin'] = 1
                template_values['urla'] = '_ah/admin/'
                template_values['url_admin'] = 'GAE'
                
                template_values['key_id'] = key_id
                template_values['date_created'] = date_created.strftime('%m/%d/%Y %I:%M %p')
                template_values['last_modified'] = last_modified.strftime('%m/%d/%Y %I:%M %p')
                template_values['last_modified_by'] = last_modified_by
                template_values['time_zone'] = time_zone
                template_values['start_date'] = start_date.strftime('%m/%d/%Y %I:%M %p')
                template_values['stop_date'] = stop_date.strftime('%m/%d/%Y %I:%M %p')
                template_values['follow_up_num'] = follow_up_num
                template_values['interval'] = interval
        else:
            template_values = get_templ_vals()
            url = users.create_login_url(self.request.uri)
            template_values['url'] = url
            template_values['url_linktext'] = 'Login'
               
        template = jinja_environment.get_template('editschedule.html')
        self.response.out.write(template.render(template_values))
        
    def post(self):
        
        key_id = int(self.request.get('id'))      
        time_zone = self.request.get('time_zone')
        start_date = datetime.datetime.strptime(self.request.get('start_date'), tformatalt)
        stop_date = datetime.datetime.strptime(self.request.get('stop_date'), tformatalt)
        follow_up_num = int(self.request.get('follow_up_num'))
        interval = self.request.get('interval')
        
        newpost = emailScheduleById(key_id)
        
        newpost.time_zone = time_zone
        newpost.start_date = start_date
        newpost.stop_date = stop_date
        newpost.follow_up_num = follow_up_num

        if interval == '':
            newpost.interval = None
        else:
            newpost.interval = int(interval)
          
        newpost.put()
        
        self.redirect('/addschedule')


class deleteEmailSchedule(webapp2.RequestHandler):
    """  Deletes project parameters and timeline info from emailSchedule table via an html form  """
    def post(self):
        key_id = int(self.request.get('id'))
        newpost = emailScheduleById(key_id)
        newpost.delete()
        self.redirect('/addschedule')


class addEmailSettings(webapp2.RequestHandler):
    """ Adds email settings info to emailSettings table via an html form """
    def get(self):
        email_settings = emailSettings.all()
        
        if users.get_current_user():
            template_values = get_templ_vals()
            url = users.create_logout_url(self.request.uri)
            template_values['url'] = url
            template_values['admin'] = 0
            
            if users.is_current_user_admin():
                template_values['download'] = ejs_exist()                     
                template_values['admin'] = 1
                template_values['urla'] = '_ah/admin/'
                template_values['url_admin'] = 'GAE'
                template_values['settings'] = email_settings                  
        else:
            template_values = get_templ_vals()
            url = users.create_login_url(self.request.uri)
            template_values['url'] = url
            template_values['url_linktext'] = 'Login'
        
        template = jinja_environment.get_template('addsettings.html')
        self.response.out.write(template.render(template_values))
        
    def post(self):
        template_values = get_templ_vals()
        url = users.create_logout_url(self.request.uri)
        template_values['url'] = url
        template_values['admin'] = 1
        template_values['urla'] = '_ah/admin/'
        template_values['url_admin'] = 'GAE'
        
        settings_query = emailSettings.all()
        template_values['settings'] = settings_query
        
        from_email = str(self.request.get('from_email'))
        email_settings = emailSettings(key_name=from_email)
        
        email_settings.from_email = from_email
        email_settings.survey_name = str(self.request.get('survey_name'))
        
        # Takes into account blank fields and sets them to None
        surveyid = self.request.get('survey_id')        
        if surveyid == '':
            email_settings.survey_id = None
        else:
            email_settings.survey_id = surveyid
        
        subjecttxt = self.request.get('subject_txt')
        if subjecttxt == '':
            email_settings.subject_txt = None
        else:
            email_settings.subject_txt = subjecttxt
        
        email_settings.from_name = str(self.request.get('from_name'))

        email_settings.put()
        
        template = jinja_environment.get_template('addsettings.html')
        self.response.out.write(template.render(template_values))


class editEmailSettings(webapp2.RequestHandler):
    """  Edits email settings info in emailSettings table via an html form """
    def get(self):
        
        from_email = self.request.get('id')
        newpost = emailSettingsByKeyName(from_email)
        
        date_created = newpost.date_created
        last_modified = newpost.last_modified 
        last_modified_by = newpost.last_modified_by
        survey_name = newpost.survey_name
        survey_id = newpost.survey_id 
        from_name = newpost.from_name
        subject_txt = newpost.subject_txt
        from_email = newpost.key().name()
               
        if users.get_current_user():
            template_values = get_templ_vals()
            url = users.create_logout_url(self.request.uri)
            template_values['url'] = url
            template_values['admin'] = 0
            
            if users.is_current_user_admin():
                template_values['download'] = ejs_exist()                  
                template_values['admin'] = 1
                template_values['urla'] = '_ah/admin/'
                template_values['url_admin'] = 'GAE'
                
                template_values['from_email'] = from_email
                template_values['date_created'] = date_created.strftime('%m/%d/%Y %I:%M %p')
                template_values['last_modified'] = last_modified.strftime('%m/%d/%Y %I:%M %p')
                template_values['last_modified_by'] = last_modified_by
                template_values['survey_name'] = survey_name
                template_values['survey_id'] = survey_id
                template_values['from_name'] = from_name
                template_values['subject_txt'] = subject_txt           
        else:
            template_values = get_templ_vals()
            url = users.create_login_url(self.request.uri)
            template_values['url'] = url
            template_values['url_linktext'] = 'Login'
        
        template = jinja_environment.get_template('editsettings.html')
        self.response.out.write(template.render(template_values))
        
    def post(self):
        
        from_email = self.request.get('id')
        survey_name = self.request.get('survey_name')
        survey_id = self.request.get('survey_id')
        from_name = self.request.get('from_name')
        subject_txt = self.request.get('subject_txt')
        
        newpost = emailSettingsByKeyName(from_email)
        
        newpost.survey_name = survey_name
        
        newpost.from_name = from_name
        
        if survey_id == '':
            newpost.survey_id = None
        else:
            newpost.survey_id = survey_id
        
        if subject_txt == '':
            newpost.subject_txt = None
        else:
            newpost.subject_txt = subject_txt
        
        newpost.put()
        
        self.redirect('/addsettings')


class deleteEmailSettings(webapp2.RequestHandler):
    """  Deletes email settings info from emailSettings table via an html form """
    def post(self):
        from_email = self.request.get('id')
        newpost = emailSettingsByKeyName(from_email)
        newpost.delete()
        self.redirect('/addsettings')


class addMessageIDs(webapp2.RequestHandler):
    """ Adds follow-up info to messageIDs table via an html form """
    def get(self):
        # pipes values from settings into form if they exist
        settings_query = emailSettings.all()
        if settings_query.count() == 1:
            subject_txt = settings_query[0].subject_txt
            survey_id = settings_query[0].survey_id
        else:
            subject_txt = None
            survey_id = None
        
        messages = messageIDs.all()
        messages.order('fu_period')
        
        # validation of follow-up messages number
        message_count = messages.count()
        schedule_query = emailSchedule.all()
        
        try:
            follow_up_number = schedule_query[0].follow_up_num
        except:
            follow_up_number = 0
            
        follow_up_val = 0
        if follow_up_number < message_count:
            follow_up_val = 1
        else:
            follow_up_val = 0
        
        if users.get_current_user():
            template_values = get_templ_vals()
            url = users.create_logout_url(self.request.uri)
            template_values['url'] = url
            template_values['admin'] = 0
            
            if users.is_current_user_admin():
                template_values['download'] = ejs_exist()                  
                template_values['admin'] = 1
                template_values['urla'] = '_ah/admin/'
                template_values['url_admin'] = 'GAE'
                
                template_values['messages'] = messages
                template_values['subject_txt'] = subject_txt
                template_values['survey_id'] = survey_id 
                template_values['follow_up_val'] = follow_up_val 
        else:
            template_values = get_templ_vals()
            url = users.create_login_url(self.request.uri)
            template_values['url'] = url
            template_values['url_linktext'] = 'Login'

        template = jinja_environment.get_template('addmessageids.html')
        self.response.out.write(template.render(template_values))
        
    def post(self):
        template_values = get_templ_vals()
        url = users.create_logout_url(self.request.uri)
        template_values['url'] = url
        template_values['admin'] = 1
        template_values['urla'] = '_ah/admin/'
        template_values['url_admin'] = 'GAE'
        
        messages = messageIDs.all()
        template_values['messages'] = messages
        
        message_id = str(self.request.get('message_id'))
        message_ids = messageIDs(key_name=message_id)
        
        message_ids.message_id = message_id
        
        # Queries settings to see if there is a survey id and/or subject text specified. If there isn't, it gets the values from form
        settings_query = emailSettings.all()
        settings_query.order('date_created')
        survey_id = settings_query[0].survey_id
        subject_txt = settings_query[0].subject_txt
        
        if survey_id is not None:
            message_ids.survey_id = survey_id
        else:
            message_ids.survey_id = self.request.get('survey_id')
        
        if subject_txt is not None:
            message_ids.subject_txt = subject_txt
        else:
            message_ids.subject_txt = self.request.get('subject_txt')

        fu_period = int(self.request.get('fu_period'))
        message_ids.fu_period = fu_period
        
        # Queries schedule to see if there is a interval (number of days between each follow-up) specified. If there is, it multiplies the follow-up number with the interval
        schedule_query = emailSchedule.all()
        schedule_query.order('date_created')
        interval = schedule_query[0].interval
        
        if interval is not None:
            message_ids.days_since = int(fu_period * interval)
        else:
            message_ids.days_since = int(self.request.get('days_since'))      
        
        reminder_number = int(self.request.get('reminder_number'))
        reminder_days = int(self.request.get('reminder_days'))
        reminder_message_id = self.request.get('reminder_message_id')
        if reminder_number > 0 and reminder_days > 0:
            message_ids.reminder_number = reminder_number
            message_ids.reminder_days = reminder_days 
            message_ids.reminder_message_id = reminder_message_id
            
        message_ids.put()
        
        template = jinja_environment.get_template('addmessageids.html')
        self.response.out.write(template.render(template_values))


class editMessageIDs(webapp2.RequestHandler):
    """  Edits follow-up info in messageIDs table via an html form """
    def get(self):
        message_id = self.request.get('id')
        newpost = messageIDByKeyName(message_id)
        
        date_created = newpost.date_created
        last_modified = newpost.last_modified 
        last_modified_by = newpost.last_modified_by
        
        subject_txt = newpost.subject_txt
        survey_id = newpost.survey_id
        days_since = newpost.days_since
        fu_period = newpost.fu_period
        message_id = newpost.key().name()
        
        reminder_number = newpost.reminder_number
        reminder_days = newpost.reminder_days
        reminder_message_id = newpost.reminder_message_id
        
        if users.get_current_user():
            template_values = get_templ_vals()
            url = users.create_logout_url(self.request.uri)
            template_values['url'] = url
            template_values['admin'] = 0
            
            if users.is_current_user_admin():
                template_values['download'] = ejs_exist()                   
                template_values['admin'] = 1
                template_values['urla'] = '_ah/admin/'
                template_values['url_admin'] = 'GAE'
                
                template_values['message_id'] = message_id 
                template_values['subject_txt'] = subject_txt
                template_values['date_created'] = date_created.strftime('%m/%d/%Y %I:%M %p')
                template_values['last_modified'] = last_modified.strftime('%m/%d/%Y %I:%M %p')
                template_values['last_modified_by'] = last_modified_by
                template_values['survey_id'] = survey_id
                template_values['days_since'] = days_since
                template_values['fu_period'] = fu_period
                template_values['reminder_number'] = reminder_number
                template_values['reminder_days'] = reminder_days
                template_values['reminder_message_id'] = reminder_message_id
                
        else:
            template_values = get_templ_vals()
            url = users.create_login_url(self.request.uri)
            template_values['url'] = url
            template_values['url_linktext'] = 'Login'
       
        template = jinja_environment.get_template('editmessageids.html')
        self.response.out.write(template.render(template_values))
        
    def post(self):
        message_id = self.request.get('id')
        subject_txt = self.request.get('subject_txt')
        survey_id = self.request.get('survey_id')
        fu_period = int(self.request.get('fu_period'))
        days_since = int(self.request.get('days_since'))
        reminder_number = int(self.request.get('reminder_number'))
        reminder_days = int(self.request.get('reminder_days'))
        reminder_message_id = self.request.get('reminder_message_id')
        
        newpost = messageIDByKeyName(message_id)
        
        newpost.subject_txt = subject_txt
        newpost.survey_id = survey_id
        newpost.fu_period = fu_period
        newpost.days_since = days_since
        newpost.reminder_number = reminder_number
        newpost.reminder_days = reminder_days
        newpost.reminder_message_id = reminder_message_id
        
        newpost.put()
        self.redirect('/addmessageids')


class deleteMessageIDs(webapp2.RequestHandler):
    """  Deletes follow-up info from messageIDs table via an html form """
    def post(self):
        message_id = self.request.get('id')
        newpost = messageIDByKeyName(message_id)
        newpost.delete()
        self.redirect('/addmessageids')


def getPanelParse(recipient_id, access_data, follow_up_number, fu_dict, interval, email_jobs):
    """ Adds new participant data from the Qualtrics panel to the emailJobs table """
    
    data = {}
    
    data['Request'] = 'getPanel'
    data['User'] = str(access_data['User'])
    data['Token'] = str(access_data['Token'])
    data['Version'] = '2.5'
    data['Format'] = 'XML'
    data['LibraryID'] = str(access_data['LibraryID'])
    data['PanelID'] = str(access_data['PanelID']) 
    data['RecipientHistory'] = '0'
    data['Subscribed'] = '0'
    
    url = 'https://new.qualtrics.com/WRAPI/ControlPanel/api.php'
    url_values = urllib.urlencode(data)
    full_url = url + '?' + url_values
    
    try:
        thedata = urllib2.urlopen(full_url) #for parsing XML
        
        tree = objectify.parse(thedata)  #for parsing XML
        root = tree.getroot()
        
        Recipients = len(root.Recipient)
        people = root.Recipient
           
        for i in range(0, Recipients):
            recipient = people[i]
            ED = recipient.EmbeddedData
            recipientid = recipient.RecipientID.text
            triggerid = ED.TriggerResponseID.text
                
            if recipient_id == recipientid: #compares TriggerResponseID in Panel to taskqueue list
                unsubscribed = recipient.Unsubscribed.text
                start_date_local = ED.STARTDATE.text
                consent = ED.CONSENTDATE.text
                test_data = int(ED.TESTDATA.text)
                
                email_jobs.recipient_id = recipient_id 
                email_jobs.trigger_id = triggerid
                email_jobs.test_data = test_data
                email_jobs.unsubscribed = int(unsubscribed)
                
                if consent != None:
                    email_jobs.start_date_local = datetime.datetime.strptime(start_date_local, tformatl)
                    email_jobs.consent_date = datetime.datetime.strptime(consent, tformatl)
                    email_jobs.fu_period = int(ED.FUPERIOD.text)
                    
                    for i in range(1, follow_up_number + 1):
                        i = str(i)
                        
                        follow_up_date_xml = 'FU' + i + 'DATE'
                        fu_check = getattr(ED, follow_up_date_xml)
                        
                        fu_date = datetime.datetime.strptime(str(fu_check), tformatl)
                        
                        fu_date_str = 'fu' + i
                        
                        setattr(email_jobs, fu_date_str, fu_date)
                         
                else:
                    email_jobs.fu_period = 999 # This is for people who most likely had their JavaScript turned off (this is in the TO-DO list)
                               
    except urllib2.HTTPError as e:
        print e.code
        print e.read()
    

class storePanel(webapp2.RequestHandler):
    """ Task queue that queries Qualtrics panel for new participants """
    
    def store_emails(self, recipients, access_data, follow_up_number, fu_dict, interval):
        for key_name in recipients:
            db.run_in_transaction(emailJobs.addto_datastore, key_name, access_data, follow_up_number, fu_dict, interval)
            
    def get(self):
        
        if is_study_active() == 1:
            data = {}
            access_data = qualtricsCall(data)
            
            # get number of follow-ups to put a limit to fu_period
            schedule_query = emailSchedule.all()
            follow_up_number = schedule_query[0].follow_up_num
            
            interval = 0
            fu_dict = {}
            
            if schedule_query[0].interval is not None:
                interval = schedule_query[0].interval
            else:
                message_query = messageIDs.all()
                message_query.order('fu_period')
                
                for i in range(0, follow_up_number):
                    fu_dict[int(message_query[i].days_since)] = int(message_query[i].fu_period)
                
            data['Request'] = 'getPanel'        
            data['User'] = str(access_data['User']) 
            data['Token'] = str(access_data['Token']) 
            data['LibraryID'] = str(access_data['LibraryID']) 
            data['PanelID'] = str(access_data['PanelID'])
            data['RecipientHistory'] = '0'
            
            # Checks to see if there are any records in the lastRecipientID table. If there aren't, it doesn't include this in the Qualtrics REST API call
            last_id_query = lastRecipientID.all()
            if last_id_query.count() > 0:
                last_id_query.order('-date_created')
                last_id = last_id_query[0].last_recipientid
                data['LastRecipientID'] = last_id
        
            data['NumberOfRecords'] = '50' # added to minimize processing time                
            data['Subscribed'] = '0'
            
            url = 'https://new.qualtrics.com/WRAPI/ControlPanel/api.php'
            url_values = urllib.urlencode(data)
            full_url = url + '?' + url_values

            try:
                thedata = urllib2.urlopen(full_url) #for parsing XML
                                    
                tree = objectify.parse(thedata)  #for parsing XML
                root = tree.getroot()
            
                if hasattr(root, 'Recipient'):
                
                    Recipients = len(root.Recipient)              
                    people = root.Recipient
            
                    q = taskqueue.Queue('getpanel') #Task
            
                    for i in range(0, Recipients):
                        recipient = people[i]
                        recipientid = recipient.RecipientID.text
                                  
                        # Updates lastRecipientID table with the last RecipientID to be used for the next REST API call
                        if i == Recipients - 1: # Sees if the recipient is the last one on the list and if so:
                            downloaded = i + 1
                            lastrecipient = lastRecipientID(key_name=recipientid, last_recipientid=recipientid, number_downloaded=downloaded)
                            lastrecipient.put()
                
                        q.add(taskqueue.Task(payload=recipientid, method='PULL'))
                                        
                    while True:
                        tasks = q.lease_tasks(300, 100)
                        if not tasks:
                            #self.error(500)
                            return
                        # accumulate tasks in memory
                        recipients = []
                        for t in tasks:
                            recipients.append(t.payload)
                        self.store_emails(recipients, access_data, follow_up_number, fu_dict, interval)
                
                        q.delete_tasks(tasks)
                           
                else:
                    pass
                
            except urllib2.HTTPError as e:
                print e.code
                print e.read()

        else:
            pass


def update_unsub(recipient_id):
    """ Updates  in Datastore """
    db.run_in_transaction(emailJobs.update_unsub, recipient_id)


class getUnsub(webapp2.RequestHandler):
    """ Updates unsubscribed participants in emailJobs table """

    def get(self):
        """ Checks for unsubscribed participants in Qualtrics panel and compares to GAE Datastore"""
        
        if is_study_active() == 1:
            gae_list = [] #List of unsubscribed participants from GAE Datastore
            
            email_job_query = emailJobs.all()
            email_job_query.order('-unsubscribed')
            
            for part in email_job_query:
                recipient_id = str(part.recipient_id)
                unsubscribed = part.unsubscribed
                if unsubscribed == 1:
                    gae_list.append(recipient_id)
            
            qualtrics_list = [] #List of unsubscribed participants from Qualtrics panel
            
            data = {}
            access_data = qualtricsCall(data)
    
            data['Request'] = 'getPanel'        
            data['User'] = str(access_data['User']) 
            data['Token'] = str(access_data['Token']) 
            data['LibraryID'] = str(access_data['LibraryID']) 
            data['PanelID'] = str(access_data['PanelID'])
            data['RecipientHistory'] = '0'
            data['Unsubscribed'] = '1'
        
            url = 'https://new.qualtrics.com/WRAPI/ControlPanel/api.php'
            
            url_values = urllib.urlencode(data)
            full_url = url + '?' + url_values
            
            try:
                thedata = urllib2.urlopen(full_url) #for parsing XML
                
                tree = objectify.parse(thedata)  #for parsing XML
                root = tree.getroot()
            
                if hasattr(root, 'Recipient'):
                    Recipients = len(root.Recipient)
                    people = root.Recipient
        
                    for i in range(0, Recipients):
                        recipient = people[i]
                        recipient_id = recipient.RecipientID.text       
                        unsub = recipient.Unsubscribed.text
                        if unsub == '1':
                            qualtrics_list.append(recipient_id)
            
                    gae_list_len = len(gae_list)
                    qual_list_len = len(qualtrics_list)
            
                    if gae_list_len != qual_list_len:
                        for i in range(qual_list_len):
                            if qualtrics_list[i] not in gae_list:
                                deferred.defer(update_unsub, qualtrics_list[i])       
                    else:
                        pass
    
                else:
                    pass
                
            except urllib2.HTTPError as e:
                print e.code
                print e.read()
            
        else:
            pass
    
        
def update_qualfuperiod(recipient_id, fup):
    data = {}
    access_data = qualtricsCall(data)
    
    data['Request'] = 'updateRecipient'
    data['User'] = str(access_data['User'])
    data['Token'] = str(access_data['Token'])
    data['RecipientID'] = recipient_id
    data['LibraryID'] = str(access_data['LibraryID'])
    data['ED[FUPERIOD]'] = fup
    
    url = 'https://new.qualtrics.com/WRAPI/ControlPanel/api.php'
    url_values = urllib.urlencode(data)
    full_url = url + '?' + url_values
    
    req = urllib2.Request(full_url)
    
    try:
        urllib2.urlopen(req)
    except urllib2.HTTPError as e:
        print e.code
        print e.read()


def update_fuperiod(recipient_id, fup):
    """ Updates fuperiod in emailJobs table """
    db.run_in_transaction(emailJobs.update_fu, recipient_id, fup)


class updateFollowUp(webapp2.RequestHandler):
    """ Queries emailJobs table for follow-up dates and updates them for current follow-up period """
    def get(self):
        
        if is_study_active() == 1:
        
            now = datetime.datetime.now()
            now_dt = now.date() #today's date to compare with follow-up dates
            
            schedule_query = emailSchedule.all()
            follow_up_num = schedule_query[0].follow_up_num
            
            interval = 0
                
            if schedule_query[0].interval is not None:
                interval = schedule_query[0].interval
            else:
                message_query = messageIDs.all()
                message_query.order('fu_period')
                    
                fu_dict = {}
                    
                for i in range(0, follow_up_num):
                    fu_dict[int(message_query[i].days_since)] = int(message_query[i].fu_period)
            
            email_job_query = emailJobs.all()
            email_job_query.filter('fu_period <', follow_up_num)  #Filter out people who have reached the last follow-up period to speed up queries (regex?)
            email_job_query.filter('fu_period !=', None)
        
            for part in email_job_query:
                recipient_id = str(part.recipient_id)
                consent = part.consent_date # This might have to be given a generic name
                
                fu_period = int(part.fu_period)
                
                consent_date = consent.date()
                calcdTime = now_dt - consent_date
                days_since = calcdTime.days
                
                fup = 0
                
                if schedule_query[0].interval is not None:
                    fup = days_since/interval # Number of days since consent date (this can be interval if it's a constant)
                else:                
                    if days_since > fu_dict.keys()[-1]:
                        fup = fu_dict[fu_dict.keys()[-1]] + 1   # Add one beyond final follow-up to indicated the follow-up is over 
                    else:                
                        for k in fu_dict.iterkeys():
                            if k > days_since:
                                break
                            elif k == days_since:
                                fup = fu_dict[days_since]
                            else:
                                fup = fu_dict[k]
                                  
                if fup != fu_period:
                    #update_qualfuperiod(recipient_id, fup) # updates follow-up period in Qualtrics panel
                    deferred.defer(update_qualfuperiod, recipient_id, fup) # updates follow-up period in Qualtrics panel (uses deferred)
                    deferred.defer(update_fuperiod, recipient_id, fup)  # updates follow-up period in GAE datastore
                else:
                    pass
        else:
            pass

def store_datesent(recipient_id, follow_up, send_date_utc):
    db.run_in_transaction(emailJobs.update_fusent, recipient_id, follow_up, send_date_utc)


def send_fuemail(access_data, time_zone, message_ids_dict, recipient_id, follow_up):
    """  Sends follow-up emails """
    # Dictionary of follow-up message IDs
    message_id = message_ids_dict[follow_up]
    
    now = datetime.datetime.now()
    send_date_utc = timeStamp(now)
    zone = datetime.datetime.now(tz=ustimezone.Mountain) # send out from Mountain time zone (Qualtrics is in Utah)
    send_date = str(datetime.datetime(zone.year, zone.month, zone.day, zone.hour, zone.minute, zone.second))
    
    settings_data = settingData()
    from_email = settings_data['from_email']
    from_name = settings_data['from_name']
    
    message_data = messageData(follow_up)
    survey_id = str(message_data[0])
    subject_txt = str(message_data[1])
    
    data = {}
    access_data = qualtricsCall(data)
    
    data['Request'] = 'sendSurveyToIndividual'
    data['User'] = str(access_data['User'])
    data['Token'] = str(access_data['Token'])
    data['SurveyID'] = survey_id
    data['SendDate'] = send_date
    data['FromEmail'] = from_email
    data['FromName'] = from_name
    data['Subject'] = subject_txt
    data['MessageID'] = message_id
    data['MessageLibraryID'] = str(access_data['LibraryID'])
    data['PanelID'] = str(access_data['PanelID'])
    data['PanelLibraryID'] = str(access_data['LibraryID'])
    data['RecipientID'] = recipient_id
    
    url = 'https://new.qualtrics.com/WRAPI/ControlPanel/api.php'
    url_values = urllib.urlencode(data)
    full_url = url + '?' + url_values
    
    req = urllib2.Request(full_url)
    
    try:
        urllib2.urlopen(req)
        store_datesent(recipient_id, follow_up, send_date_utc)
        status = 1
        return status
    except urllib2.HTTPError as e:
        status = 0
        print e.code
        print e.read()
        return status
    
        
class sendFollowUp(webapp2.RequestHandler):
    """ Queries Datastore for follow-up dates that match today's date, then adds them to a task queue """
    
    def get(self):
        if is_study_active() == 1:
            now = datetime.datetime.now() # get current UTC datetime
            now_date = now.date() #today's date to compare with follow-up dates
            
            data = {}
            access_data = qualtricsCall(data)
            
            email_job_query = emailJobs.all()
            email_job_query.filter('fu_period >', 0)
            email_job_query.filter('fu_period <', 999)
            
            schedule_query = emailSchedule.all()
            fup_num = schedule_query[0].follow_up_num
            time_zone = schedule_query[0].time_zone
            
            message_ids_query = messageIDs.all()
            message_ids_query.order('fu_period')
            message_ids_dict = {}
            for i in range(0, fup_num):
                
                fu_period = int(message_ids_query[i].fu_period)
                message_id = str(message_ids_query[i].message_id)
                 
                message_ids_dict[fu_period] = message_id
            
            for part in email_job_query:
                unsubscribed = part.unsubscribed
                
                if unsubscribed is not 1:
                    for i in range(1, fup_num + 1):
                        i = str(i)
                        
                        follow_up_sent = 'fu' + i + '_email_sent'
                        fu_check = getattr(part, follow_up_sent)
    
                        if part.fu_period == int(i) and fu_check == None:
                            recipient_id = str(part.recipient_id)
                            #recipient_lang = str(part.recipient_lang)  # TODO: Optional, not used
                            
                            follow_up_date = 'fu' + i
                            fu_raw_date = getattr(part, follow_up_date)
                            
                            fu_date = fu_raw_date.date()
                            if fu_date == now_date:
                                follow_up = int(i)
                                deferred.defer(send_fuemail, access_data, time_zone, message_ids_dict, recipient_id, follow_up)
                            else:
                                pass
        else:
            pass
                            

class sendMissedFU(webapp2.RequestHandler):
    """ Queries emailJobs table for follow-up emails that were missed, then adds them to a task queue so that an email can be sent out """
    
    def get(self):
        if is_study_active() == 1:
            
            now = datetime.datetime.now() # get current UTC datetime
            now_date = now.date() #today's date to compare with follow-up dates
            
            data = {}
            access_data = qualtricsCall(data)
    
            schedule_query = emailSchedule.all()
            follow_up_num = schedule_query[0].follow_up_num
            time_zone = schedule_query[0].time_zone
            
            message_query = messageIDs.all()
            message_query.order('fu_period')
            
            fu_dict = {}
                
            for i in range(follow_up_num):
                fu_dict[int(message_query[i].days_since)] = int(message_query[i].fu_period)
            
            message_ids_dict = {}
            for i in range(0, follow_up_num):
                
                fu_period = int(message_query[i].fu_period)
                message_id = str(message_query[i].message_id)
                 
                message_ids_dict[fu_period] = message_id
            
            email_job_query = emailJobs.all()
            email_job_query.filter('fu_period <', follow_up_num + 1)  #Filter out people who have reached the last follow-up period to speed up queries
            #q.filter('fu_period <', 999) # Find a way to filter out people who have no fu_period
            email_job_query.filter('fu_period !=', None)
    
            for part in email_job_query:
                #recipient_lang = part.recipient_lang
                recipient_id = part.recipient_id
                fu_period = int(part.fu_period)
                unsubscribed = part.unsubscribed
                consent = part.consent_date
                
                consent_date = consent.date()
                calcdTime = now_date - consent_date
                days_since = calcdTime.days
                
                sorted(fu_dict, key=fu_dict.get) # sort fu dictionary by keys (days after consent)
                
                for k in fu_dict.iterkeys():
                    if k > days_since:
                        break
                    else:
                        follow_up = fu_dict[k]
                        followup = 'fu' + str(follow_up) + '_email_sent'
                        fu_check = getattr(part, followup)  # part.fu1_email_sent
                        
                        if fu_check == None and unsubscribed == 0: # if the follow-up for this period hasn't been sent and the person isn't unsub                           
                            deferred.defer(send_fuemail, access_data, time_zone, message_ids_dict, recipient_id, follow_up)
                    
        else:
            pass


class fuCheckUp(webapp2.RequestHandler):
    """ Creates a csv file for download to test whether all follow-ups are being sent when scheduled """
    def get(self):
        
        schedule_query = emailSchedule.all()
        follow_up_num = schedule_query[0].follow_up_num
        time_zone = schedule_query[0].time_zone
        
        if time_zone == 'Eastern':
            zone = datetime.datetime.now(tz=ustimezone.Eastern) # get current Eastern datetime
        elif time_zone == 'Central':
            zone = datetime.datetime.now(tz=ustimezone.Central) # get current Central datetime
        elif time_zone == 'Mountain':
            zone = datetime.datetime.now(tz=ustimezone.Mountain) # get current Mountain datetime
        else:
            zone = datetime.datetime.now(tz=ustimezone.Pacific) # get current Pacific datetime
            
        download_date = str(datetime.date(zone.year, zone.month, zone.day))
        
        email_job_query = emailJobs.all()
        email_job_query.order('consent_date')
        
        header_tuple = ('last_modified', 'trigger_id', 'recipient_id', 'test_data', 'unsubscribe', 'unsubscribe_date', 'start_date_local', 'consent_date', 'fu_period', 'last_fu_sent')
        data_tuples = ()
        variable_list = []
        
        for i in range(1, follow_up_num + 1):
            i = str(i)
            
            fu_due = 'fu' + i
            fu_sent = 'fu' + i + '_email_sent'
            
            variable_list.append(fu_due)
            variable_list.append(fu_sent)
            
            data_tuples = data_tuples + (fu_due, fu_sent)
        
        final_data_tuple = header_tuple + data_tuples
        data = [final_data_tuple]
        
        for part in email_job_query:
            last_modified_dt = part.last_modified
            last_modified = last_modified_dt.strftime(tformatl)
            trigger_id = str(part.trigger_id)
            recipient_id = str(part.recipient_id)
            test_data = int(part.test_data)
            unsubscribed = str(part.unsubscribed)
            unsubscribe_date = str(part.unsubscribe_date)
            start_date_local = str(part.start_date_local)
            consent_date = str(part.consent_date)
            fu_period = str(part.fu_period)
            last_fu_sent = str(part.last_fu_sent)
            
            var_list = []
            
            for var in variable_list:
                fu_var = getattr(part, var)
                var_list.append(str(fu_var))
            
            var_tuple = tuple(var_list)
            
            fixed_tuple = (last_modified, trigger_id, recipient_id, test_data, unsubscribed, unsubscribe_date, start_date_local, consent_date, fu_period, last_fu_sent)
            csv_tuple = fixed_tuple + var_tuple
            
            data.append((csv_tuple))
            
        self.response.headers['Content-Type'] = 'application/csv'
        self.response.headers['Content-Disposition'] = 'attachment;filename=fucheckup_' + download_date + '.csv'
        writer = csv.writer(self.response.out)
    
        for item in data:
            writer.writerow(item)


class sendEmail(webapp2.RequestHandler):
    """ Page with form to send participants an email with a follow-up survey link """
    
    def get(self):
        if users.get_current_user():
            template_values = get_templ_vals()
            url = users.create_logout_url(self.request.uri)
            template_values['url'] = url
            template_values['admin'] = 0
            
            if users.is_current_user_admin():
                ejs = emailJobs.all()
                template_values['download'] = ejs_exist()                  
                template_values['admin'] = 1
                template_values['urla'] = '_ah/admin/'
                template_values['url_admin'] = 'GAE'
                
                message_ids_query = messageIDs.all()
                message_ids_query.order('fu_period')
                fu_len = message_ids_query.count()
                
                message_ids_dict = {}
                
                for i in range(fu_len):
                    fu_period = int(message_ids_query[i].fu_period)
                    message_id = str(message_ids_query[i].message_id)
                    message_ids_dict[fu_period] = message_id              
                
                template_values['message_ids_dict'] = json.dumps(message_ids_dict) 
                template_values['message_ids'] = message_ids_dict
                template_values['messages_len'] = fu_len
        else:
            template_values = get_templ_vals()
            url = users.create_login_url(self.request.uri)
            template_values['url'] = url
            template_values['url_linktext'] = 'Login'

        template = jinja_environment.get_template('sendemail.html')
        self.response.out.write(template.render(template_values))

    def post(self):
        template_values = get_templ_vals()
        url = users.create_logout_url(self.request.uri)
        template_values['url'] = url
        template_values['admin'] = 1
        template_values['urla'] = '_ah/admin/'
        template_values['url_admin'] = 'GAE'
        
        data = {}
        access_data = qualtricsCall(data)
        
        schedule_query = emailSchedule.all()
        time_zone = schedule_query[0].time_zone
        
        message_ids_query = messageIDs.all()
        message_ids_query.order('fu_period')
        fu_len = message_ids_query.count()
        
        message_ids_dict = {}
        
        recipient_id = self.request.get('guid') # will be used to update the fu sent date in the datastore
        follow_up = int(self.request.get('follow_up'))
        lang = self.request.get('lang') # TODO: This will be optional
        
        for i in range(fu_len):
            fu_period = int(message_ids_query[i].fu_period)
            message_id = str(message_ids_query[i].message_id)
             
            message_ids_dict[fu_period] = message_id
        
        template_values['messages_len'] = fu_len
        
        status = send_fuemail(access_data, time_zone, message_ids_dict, recipient_id, follow_up) # TODO: status of trying to send email (1 = success, 0 = error), this is passed along to template
        
        template_values['status'] = status # status added to template_value dictionary to be used by conditional display of result message
         
        template = jinja_environment.get_template('sendemail.html')
        self.response.out.write(template.render(template_values))
        
app = webapp2.WSGIApplication([
                               ('/', MainPage),
                               
                               ('/cron/getpanelworker', storePanel),
                               ('/cron/updatefu', updateFollowUp),
                               ('/cron/sendfu', sendFollowUp),
                               ('/cron/missedfu', sendMissedFU),
                               ('/cron/getunsub', getUnsub),
                               ('/fucheckup', fuCheckUp),

                               ('/addqualaccess', addQualtricsAccessInfo),
                               ('/editqualaccess', editQualtricsAccessInfo),
                               ('/deletequalaccess', deleteQualtricsAccessInfo),
                               
                               ('/addschedule', addEmailSchedule),
                               ('/editschedule', editEmailSchedule),
                               ('/deleteschedule', deleteEmailSchedule),
                               
                               ('/addsettings', addEmailSettings),
                               ('/editsettings', editEmailSettings),
                               ('/deletesettings', deleteEmailSettings),
                               
                               ('/addmessageids', addMessageIDs),
                               ('/editmessageids', editMessageIDs),
                               ('/deletemessageids', deleteMessageIDs),
                               
                               ('/sendemail', sendEmail),
                               ],
                               debug=True)
