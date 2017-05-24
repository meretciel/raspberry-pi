
import re
import subprocess
import os
from os import path
import hashlib
from datetime import datetime
import time
import subprocess
import shlex
import logging
import glob


_currDir = os.path.dirname( os.path.abspath( __file__ ) )

# setup logger
logging.basicConfig(level    = logging.DEBUG,
                    format   = '%(asctime)s %(name)s %(levelname)s %(message)s',
                    datefmt  = '%m-%d %H:%M',
                    filename = path.join(_currDir, "_send-emil.log"),
                    filemode ='w')

console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(name)s: %(levelname)s %(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)

logging.info( "current directory: {}".format( _currDir ) )

# settings
REQUEST_IDENTIFIER = '[request@me]'
IDLE               = 'the parser is idle'
SUBJECT            = 'hitted subject'
BEGIN              = 'beginning-of-request'
IMG_FORMAT         = 'jpg'
RQ_TAKE_PICTURE    = 'take-picture'
ARG_NUM            = 'number'
MAIL_DIR           = '/home/meretciel/mail/new'
IMG_DIR            = '/home/meretciel/workspace/camera'
RECEIVERS          = [ 'meretciel.fr@gmail.com' ]


class EmailMessage( object ):
    _COMMAND_TEMPLATE_PLAIN      = r'mail -v -s "{subject}" {receiver}'
    _COMMAND_TEMPLATE_ATTACHMENT = r'mail -v -s "{subject}" {attachment} {receiver}'

    def __init__( self, subject = None, message = None, receiver = None, attachment = None ):
        self._subject    = subject
        self._message    = message
        self._receiver   = receiver
        self._attachment = attachment

    def _generateEmailCommand( self ):
        if isinstance( self._receiver, list ):
            receiver = ';'.join( self._receiver )
        else:
            receiver = self._receiver

        if not self._attachment:
            return EmailMessage._COMMAND_TEMPLATE_PLAIN.format( message = self._message, subject = self._subject, receiver = receiver )
            

        if isinstance( self._attachment, list):
            attachment = ' -a '.join( self._attachment )
            attachment = ' -a ' + attachment

        else:
            attachment = ' -a ' + self._attachment
        

        return EmailMessage._COMMAND_TEMPLATE_ATTACHMENT.format( message = self._message, subject = self._subject, receiver = receiver, attachment = attachment )

    
    def send( self ):
        ''' send email using mail command. We can also implement this in plain python '''
        p1 = subprocess.Popen( 
            shlex.split( r'echo {message}'.format( message = self._message ) ),
            stdout = subprocess.PIPE,
        )
        p2 = subprocess.Popen(
            shlex.split( self._generateEmailCommand() ),
            stdin = subprocess.PIPE
        )
        p2.communicate()

def constructCommand( s_command ):
    l = [ x for x in s_command.split(' ') if x != '' ]
    return l 

def executeCommand( s_command ):
    logging.info( "execute command: {}".format( s_command ) )
    subprocess.call( constructCommand( s_command ) )

def getEmail():
    executeCommand( "getmail -n" )




def checkNewEmail():
    ''' check if there is new ( unread ) emails. '''
    ls_output = subprocess.check_output( constructCommand( "ls -lt {}".format( MAIL_DIR ) ) )
    ls_output = str( ls_output, "utf-8" )
    logging.debug( "ls_output: {}".format( ls_output ) )
    ls_output = ls_output.split('\n')
    ls_output = ls_output[1:]   # the first line is total output
    newFiles  = [ x.split(' ')[-1] for x in ls_output ][::-1]
    newFiles  = [ path.join( MAIL_DIR, x ) for x in newFiles if x != '' ]

    return newFiles



def takePicture( number ):
    ''' ask raspiberry pi to take picture. '''
    time            = datetime.utcnow()
    baseFileName    = path.join( IMG_DIR, hashlib.sha224( str( time ).encode( "utf-8" ) ).hexdigest() )
    commandTemplate = r'/opt/vc/bin/raspistill -n -vf -w 640 -h 480 -e {IMG_FORMAT} {_} -o {baseFileName}%04d.{IMG_FORMAT}'.format( IMG_FORMAT = IMG_FORMAT, baseFileName = baseFileName, _ = "{time}")
    number          = min( 10, int( number ) )
    number          = max( number, 1 ) 

    if number == 1:
        command = commandTemplate.format( time = '' )
        imgFileNames = [ "{baseFileName}-001.{IMG_FORMAT}".format( baseFileName = baseFileName, IMG_FORMAT = IMG_FORMAT ) ]
    else:
        _tl           = 2000    # in milliseconds
        _totalTime    = _tl * ( number - 1)
        _time         = "-t {} -tl {}".format( _totalTime, _tl )
        command       = commandTemplate.format( time = _time )

        imgFileNames = ["{baseFileName}{num}.{IMG_FORMAT}".format( baseFileName = baseFileName, num=str(i).zfill(4), IMG_FORMAT=IMG_FORMAT ) for i in range(number)]

    try:
        executeCommand( command )
        return imgFileNames
    except Exception as e:
       logging.error("Error when taking picture") 
       return []


class Request( object ):

    def __init__( self ):
        self._requestName = None
        self._args = {}

    def load( self, attrName, value ):
        if attrName == 'request':
            self._requestName = value

        else:
            self._args.update( { attrName : value } )

    def process( self ):
        if self._requestName:
            logging.info( 'processing {}'.format( self ) )

            if self._requestName.lower() == RQ_TAKE_PICTURE:
                number = self._args.get( ARG_NUM, 1 )
                imgFiles = takePicture( number )
                logging.debug( '<2> image files : {}'.format( imgFiles ) )
                newEmail = EmailMessage( subject = 'New Images', message = '', receiver = RECEIVERS, attachment = imgFiles )
                newEmail.send()
                for fn in imgFiles:
                    logging.info( "removing the file: {}".format( fn ) )
                    os.remove( fn )


    def __repr__( self ):
        return "Request( name={}, args={} )".format( self._requestName, str( self._args ) )

def _parseEmail( f, state, requests ):
    if state == IDLE:
        line = f.readline()
        while line:
            if 'Subject' in line and REQUEST_IDENTIFIER in line:
                state = SUBJECT
                break
            line = f.readline()
        return line, f, state, requests

    if state == SUBJECT:
        line = f.readline()
        while line:
            if '@begin' in line:
                state = BEGIN
                break
            line = f.readline()
        return line, f, state, requests

    if state == BEGIN:
        pattern = r'(?P<attrName>\w+)\s*=\s*(?P<value>.+)'
        line = f.readline()
        request = Request()
        while line:
            if '@end' in line:
                requests.append( request )
                state = IDLE
                break

            res = re.search( pattern, line )
            if res:
                attrName  = res.group( 'attrName' )
                value     = res.group( 'value' )
                request.load( res.group( 'attrName' ), res.group( 'value' ) )

            line = f.readline()

        return line, f, state, requests
        



def parseEmail( msgFile ):
    logging.info("parsing email file {}".format( msgFile ) )
    with open( msgFile ) as f:
        state = IDLE
        line = '__start__'
        requests = []
        while line:
            logging.info( "processing line : {}".format( line ) )
            line, f, state, request = _parseEmail( f, state, requests )

        return requests

def removeNewMsgFiles( newMsgFiles ):

    for item in newMsgFiles:
        os.remove( item )


def getNewRequestFromEmail():
    getEmail()
    newMsgFiles = checkNewEmail()
    logging.debug(" <1> New messages : {}".format( str( newMsgFiles ) ) ) 
    requests = []
    for newMsgFile in newMsgFiles:
        requests.extend( parseEmail( newMsgFile ) )
    removeNewMsgFiles( newMsgFiles )
    return requests


if __name__ == '__main__':
    
    existingFiles = glob.glob( path.join( MAIL_DIR, r'*.alarmpi' ) )
    for f in existingFiles:
        os.remove( f )

    while True:
        logging.info( "waiting for request." )
        requests = getNewRequestFromEmail()
        for request in requests:
            request.process()

        time.sleep( 10. )


