# qualms
Google App Engine extension of [Qualtrics](http://www.qualtrics.com/) email jobs for longitudinal research studies

#### Your Qualtrics authentication info

The conventions of your username are different at every institution. The example below is for UCSF. 
Qualtrics API token access must be given to you by an administrator. 

        user: sf1234#ucsf
        token: uZEDfdd938Wdzzdkeiidso



#### Changing the number of follow-ups

The default code is written for 30 follow-ups. If your project uses more, find the following lines in the main.py file and add as many follow-ups as you need following the same pattern below (i.e., follow-up 31).
        
```python
fu30 = db.DateTimeProperty()
fu31 = db.DateTimeProperty() # this adds an 31st follow-up
    
last_fu_sent = db.DateTimeProperty() # Datetime last follow-up email was sent

fu30_email_sent = db.DateTimeProperty()
fu31_email_sent = db.DateTimeProperty() # this adds date the 31st follow-up was actually sent

```

#### Example surveys
1. QUALMS-Baseline.qsf
2. QUALMS-Follow-up.qsf

