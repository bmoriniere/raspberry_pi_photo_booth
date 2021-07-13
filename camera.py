#!/usr/bin/env python
"""
Raspberry Pi Photo Booth

This code is intended to be runs on a Raspberry Pi.
Currently both Python 2 and Python 3 are supported.

You can modify the config via [camera-config.yaml].
(The 1st time the code is run [camera-config.yaml] will be created based on [camera-config.example.yaml].
"""
__author__ = 'Jibbius (Jack Barker)'
__version__ = '2.2'


#Standard imports
from time import sleep
from shutil import copy2
import pygame
import sys
import datetime
import os

#Need to do this early, in case import below fails:
REAL_PATH = os.path.dirname(os.path.realpath(__file__))

#Additional Imports
try:
    from PIL import Image
    from ruamel import yaml
    import picamera
    import RPi.GPIO as GPIO

except ImportError as missing_module:
    print('--------------------------------------------')
    print('ERROR:')
    print(missing_module)
    print('')
    print(' - Please run the following command(s) to resolve:')
    if sys.version_info < (3,0):
        print('   pip install -r ' + REAL_PATH + '/requirements.txt')
    else:
        print('   python3 -m pip install -r ' + REAL_PATH + '/requirements.txt')
    print('')
    sys.exit()

#############################
### Load config from file ###
#############################
PATH_TO_CONFIG = REAL_PATH + '/camera-config.yaml'
PATH_TO_CONFIG_EXAMPLE = REAL_PATH + '/camera-config.example.yaml'

#Check if config file exists
if not os.path.exists(PATH_TO_CONFIG):
    #Create a new config file, using the example file
    print('Config file was not found. Creating:' + PATH_TO_CONFIG)
    copy2(PATH_TO_CONFIG_EXAMPLE, PATH_TO_CONFIG)

#Read config file using YAML interpreter
with open(PATH_TO_CONFIG, 'r') as stream:
    CONFIG = {}
    try:
        CONFIG = yaml.safe_load(stream)
    except yaml.YAMLError as exc:
        print(exc)

#Required config
try:
    # Each of the following varibles, is now configured within [camera-config.yaml]:
    CAMERA_BUTTON_PIN = CONFIG['CAMERA_BUTTON_PIN']
    EXIT_BUTTON_PIN = CONFIG['EXIT_BUTTON_PIN']
    TOTAL_PICS = CONFIG['TOTAL_PICS']
    PREP_DELAY = CONFIG['PREP_DELAY']
    COUNTDOWN = CONFIG['COUNTDOWN']
    PHOTO_W = CONFIG['PHOTO_W']
    PHOTO_H = CONFIG['PHOTO_H']
    SCREEN_W = CONFIG['SCREEN_W']
    SCREEN_H = CONFIG['SCREEN_H']
    CAMERA_ROTATION = CONFIG['CAMERA_ROTATION']
    CAMERA_HFLIP = CONFIG['CAMERA_HFLIP']
    DEBOUNCE_TIME = CONFIG['DEBOUNCE_TIME']
    TESTMODE_AUTOPRESS_BUTTON = CONFIG['TESTMODE_AUTOPRESS_BUTTON']
    SAVE_RAW_IMAGES_FOLDER = CONFIG['SAVE_RAW_IMAGES_FOLDER']

except KeyError as exc:
    print('')
    print('ERROR:')
    print(' - Problems exist within configuration file: [' + PATH_TO_CONFIG + '].')
    print(' - The expected configuration item ' + str(exc) + ' was not found.')
    print(' - Please refer to the example file [' + PATH_TO_CONFIG_EXAMPLE + '], for reference.')
    print('')
    sys.exit()

#Optional config
COPY_IMAGES_TO = []
try:
    if isinstance(CONFIG["COPY_IMAGES_TO"], list):
        COPY_IMAGES_TO.extend( CONFIG["COPY_IMAGES_TO"] )
    else:
        COPY_IMAGES_TO.append( CONFIG["COPY_IMAGES_TO"] )

except KeyError as exc:
    pass


pygame.init()
pygame.mixer.init()
SOUND_APOIL = './assets/sounds/deshabillezvous.mp3'
SOUND_COUNTDOWN_1 = './assets/sounds/unedeuxtrois.mp3'
SOUND_COUNTDOWN_2 = './assets/sounds/ohisse.mp3'

SOUND_CAMERA = './assets/sounds/camera.mp3'

SOUND_DONE_0 = './assets/sounds/cestbeau.mp3'
SOUND_DONE_1 = './assets/sounds/mignonlemoustachu.mp3'
SOUND_DONE_2 = './assets/sounds/plusdeprofil.mp3'
SOUND_DONE_3 = './assets/sounds/tropgros.mp3'
SOUND_DONE_4 = './assets/sounds/moche.mp3'

##############################
### Setup Objects and Pins ###
##############################
#Setup GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(CAMERA_BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(EXIT_BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

CAMERA = picamera.PiCamera()
CAMERA.rotation = CAMERA_ROTATION
CAMERA.annotate_text_size = 80
CAMERA.resolution = (PHOTO_W, PHOTO_H)
CAMERA.hflip = CAMERA_HFLIP

########################
### Helper Functions ###
########################

def play_sound(file):
    pygame.mixer.music.load(file)
    pygame.mixer.music.play()

def health_test_required_folders():
    folders_list=[SAVE_RAW_IMAGES_FOLDER]
    folders_list.extend(COPY_IMAGES_TO)
    folders_checked=[]

    for folder in folders_list:
        if folder not in folders_checked:
            folders_checked.append(folder)
        else:
            print('ERROR: Cannot use same folder path ('+folder+') twice. Refer config file.')

        #Create folder if doesn't exist
        if not os.path.exists(folder):
            print('Creating folder: ' + folder)
            os.makedirs(folder)

def print_overlay(string_to_print):
    """
    Writes a string to both [i] the console, and [ii] CAMERA.annotate_text
    """
    print(string_to_print)
    CAMERA.annotate_text = string_to_print

def get_base_filename_for_images():
    """
    For each photo-capture cycle, a common base filename shall be used,
    based on the current timestamp.

    Example:
    ${ProjectRoot}/photos/2017-12-31_23-59-59

    The example above, will later result in:
    ${ProjectRoot}/photos/2017-12-31_23-59-59_1of4.png, being used as a filename.
    """

    base_filename = str(datetime.datetime.now()).split('.')[0]
    base_filename = base_filename.replace(' ', '_')
    base_filename = base_filename.replace(':', '-')

    base_filepath = REAL_PATH + '/' + SAVE_RAW_IMAGES_FOLDER + '/' + base_filename + '.jpg'

    return base_filepath

def remove_overlay(overlay_id):
    """
    If there is an overlay, remove it
    """
    if overlay_id != -1:
        CAMERA.remove_overlay(overlay_id)

# overlay one image on screen
def overlay_image(image_path, duration=0, layer=3, mode='RGB'):
    """
    Add an overlay (and sleep for an optional duration).
    If sleep duration is not supplied, then overlay will need to be removed later.
    This function returns an overlay id, which can be used to remove_overlay(id).
    """

    # Load the (arbitrarily sized) image
    img = Image.open(image_path)

    if( img.size[0] > SCREEN_W):
        # To avoid memory issues associated with large images, we are going to resize image to match our screen's size:
        basewidth = SCREEN_W
        wpercent = (basewidth/float(img.size[0]))
        hsize = int((float(img.size[1])*float(wpercent)))
        img = img.resize((basewidth,hsize), Image.ANTIALIAS)

    # "
    #   The camera`s block size is 32x16 so any image data
    #   provided to a renderer must have a width which is a
    #   multiple of 32, and a height which is a multiple of
    #   16.
    # "
    # Refer:
    # http://picamera.readthedocs.io/en/release-1.10/recipes1.html#overlaying-images-on-the-preview

    # Create an image padded to the required size with mode 'RGB' / 'RGBA'
    pad = Image.new(mode, (
        ((img.size[0] + 31) // 32) * 32,
        ((img.size[1] + 15) // 16) * 16,
    ))

    # Paste the original image into the padded one
    pad.paste(img, (0, 0))

    #Get the padded image data
    try:
        padded_img_data = pad.tobytes()
    except AttributeError:
        padded_img_data = pad.tostring() # Note: tostring() is deprecated in PIL v3.x

    # Add the overlay with the padded image as the source,
    # but the original image's dimensions
    o_id = CAMERA.add_overlay(padded_img_data, size=img.size)
    o_id.layer = layer

    if duration > 0:
        sleep(duration)
        CAMERA.remove_overlay(o_id)
        o_id = -1 # '-1' indicates there is no overlay

    return o_id # if we have an overlay (o_id > 0), we will need to remove it later

###############
### Screens ###
###############
def prep_for_photo_screen(photo_number):
    """
    Prompt the user to get ready for the next photo
    """

    #Get ready for the next photo
    get_ready_image = REAL_PATH + '/assets/Posez.jpg'
    overlay_image(get_ready_image, PREP_DELAY, 4, 'RGBA')

def taking_photo(photo_number, filename):
    """
    This function captures the photo
    """

    #countdown from 3, and display countdown on screen
    for counter in range(COUNTDOWN, 0, -1):
        get_ready_image = REAL_PATH + '/assets/wait-' + str(counter) + '.png'
        overlay_image(get_ready_image, 1, 3, 'RGBA')

    #Take still
    play_sound(SOUND_CAMERA)
    CAMERA.annotate_text = ''
    CAMERA.capture(filename)
    print('Photo (' + str(photo_number) + ') saved: ' + filename)
    return filename

def playback_screen(filename):
    """
    Final screen before main loop restarts
    """

    overlay_image(filename, 2, 3)

    #All done
    print('All done!')
    finished_image = REAL_PATH + '/assets/Fini.jpg'
    overlay_image(finished_image, 3)

def done_sound(photo_number):
    if(photo_number%5 == 0):
        play_sound(SOUND_DONE_0)
    elif(photo_number%5 == 1):
        play_sound(SOUND_DONE_1)
    elif(photo_number%5 == 2):
        play_sound(SOUND_DONE_2)
    elif(photo_number%5 == 3):
        play_sound(SOUND_DONE_3)
    elif(photo_number%5 == 4):
        play_sound(SOUND_DONE_4)

def main():
    """
    Main program loop
    """

    #Start Program
    print('Welcome to the photo booth!')
    print('(version ' + __version__ + ')')
    print('')
    print('Press the \'Take photo\' button to take a photo')
    print('Use [Ctrl] + [\\] to exit')
    print('')

    taken_photo = 3

    #Setup any required folders (if missing)
    health_test_required_folders()

    #Start camera preview
    CAMERA.start_preview(resolution=(SCREEN_W, SCREEN_H))

    #Display intro screen
    intro_image = REAL_PATH + '/assets/Bienvenue.jpg'
    overlay = overlay_image(intro_image, 0, 3)

    #Wait for someone to push the button
    i = 0
    blink_speed = 10

   #Use falling edge detection to see if button is being pushed in
    GPIO.add_event_detect(CAMERA_BUTTON_PIN, GPIO.FALLING)
    GPIO.add_event_detect(EXIT_BUTTON_PIN, GPIO.FALLING)

    while True:
        photo_button_is_pressed = None
        exit_button_is_pressed = None

        if GPIO.event_detected(CAMERA_BUTTON_PIN):
            sleep(DEBOUNCE_TIME)
            if GPIO.input(CAMERA_BUTTON_PIN) == 0:
                photo_button_is_pressed = True

        if GPIO.event_detected(EXIT_BUTTON_PIN):
            sleep(DEBOUNCE_TIME)
            if GPIO.input(EXIT_BUTTON_PIN) == 0:
                exit_button_is_pressed = True

        if exit_button_is_pressed is not None:
            return #Exit the photo booth

        if TESTMODE_AUTOPRESS_BUTTON:
            photo_button_is_pressed = True

        #Stay inside loop, until button is pressed
        if photo_button_is_pressed is None:
            #Regardless, restart loop
            sleep(0.1)
            continue

        #Button has been pressed!
        print('Button pressed! You folks are in for a treat.')

        #Silence GPIO detection
        GPIO.remove_event_detect(CAMERA_BUTTON_PIN)
        GPIO.remove_event_detect(EXIT_BUTTON_PIN)

        #Get filenames for images
        filename = get_base_filename_for_images()

        photo_filenames = []
        if (taken_photo%10 == 1):
            play_sound(SOUND_APOIL)

        prep_for_photo_screen(1)
        remove_overlay(overlay)
        if (taken_photo%10 != 1):

            if (taken_photo%2 == 0):
                play_sound(SOUND_COUNTDOWN_1)
            else:
                play_sound(SOUND_COUNTDOWN_2)
        fname = taking_photo(1, filename)
        photo_filenames.append(fname)

        #thanks for playing

        overlay_image(filename, 2, 3)

        #All done
        done_sound(taken_photo)
        finished_image = REAL_PATH + '/assets/Fini.jpg'
        finished_overlay = overlay_image(finished_image, 0, 4)
        overlay = overlay_image(intro_image, 0, 3)

        sleep(2)
        remove_overlay(finished_overlay)

        #Save photos into additional folders (for post-processing/backup... etc.)
        for dest in COPY_IMAGES_TO:
            for src in photo_filenames:
                print(src + ' -> ' + dest)
                copy2(src, dest)

        # If we were doing a test run, exit here.
        if TESTMODE_AUTOPRESS_BUTTON:
            break

        taken_photo += 1
        # Otherwise, display intro screen again
        GPIO.add_event_detect(CAMERA_BUTTON_PIN, GPIO.FALLING)
        GPIO.add_event_detect(EXIT_BUTTON_PIN, GPIO.FALLING)
        print('Press the button to take a photo')

if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        print('Goodbye')

    finally:
        CAMERA.stop_preview()
        CAMERA.close()
        GPIO.cleanup()
        sys.exit()
