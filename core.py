# created by KRC
# KRC Support You


import telegram
import cv2
import dlib

from PyQt5.QtCore import QTimer, QThread, pyqtSignal, QRegExp, Qt
from PyQt5.QtGui import QImage, QPixmap, QIcon, QTextCursor, QRegExpValidator
from PyQt5.QtWidgets import QDialog, QApplication, QMainWindow, QMessageBox
from PyQt5.uic import loadUi

import os
import webbrowser
import logging
import logging.config
import sqlite3
import sys
import threading
import queue
import multiprocessing
#import winsound

from configparser import ConfigParser
from datetime import datetime


class TrainingDataNotFoundError(FileNotFoundError):
    pass


class DatabaseNotFoundError(FileNotFoundError):
    pass


class CoreUI(QMainWindow):
    database = './FaceBase.db'
    trainingData = './recognizer/trainingData.yml'
    cap = cv2.VideoCapture()
    captureQueue = queue.Queue()  
    alarmQueue = queue.LifoQueue()  
    logQueue = multiprocessing.Queue()  
    receiveLogSignal = pyqtSignal(str)  

    def __init__(self):
        super(CoreUI, self).__init__()
        loadUi('./ui/Core.ui', self)
        self.setWindowIcon(QIcon('./icons/icon.png'))
        self.setFixedSize(1300, 675)

       
        self.isExternalCameraUsed = False
        self.useExternalCameraCheckBox.stateChanged.connect(
            lambda: self.useExternalCamera(self.useExternalCameraCheckBox))
        self.faceProcessingThread = FaceProcessingThread()
        self.startWebcamButton.clicked.connect(self.startWebcam)

        
        self.initDbButton.setIcon(QIcon('./icons/warning.png'))
        self.initDbButton.clicked.connect(self.initDb)

        self.timer = QTimer(self) 
        self.timer.timeout.connect(self.updateFrame)

        
        self.faceTrackerCheckBox.stateChanged.connect(
            lambda: self.faceProcessingThread.enableFaceTracker(self))
        self.faceRecognizerCheckBox.stateChanged.connect(
            lambda: self.faceProcessingThread.enableFaceRecognizer(self))
        self.panalarmCheckBox.stateChanged.connect(lambda: self.faceProcessingThread.enablePanalarm(self))

       
        self.equalizeHistCheckBox.stateChanged.connect(
            lambda: self.faceProcessingThread.enableEqualizeHist(self))

        
        self.debugCheckBox.stateChanged.connect(lambda: self.faceProcessingThread.enableDebug(self))
        self.confidenceThresholdSlider.valueChanged.connect(
            lambda: self.faceProcessingThread.setConfidenceThreshold(self))
        self.autoAlarmThresholdSlider.valueChanged.connect(
            lambda: self.faceProcessingThread.setAutoAlarmThreshold(self))

        
        self.alarmSignalThreshold = 10
        self.panalarmThread = threading.Thread(target=self.recieveAlarm, daemon=True)
        self.isBellEnabled = True
        self.bellCheckBox.stateChanged.connect(lambda: self.enableBell(self.bellCheckBox))
        self.isTelegramBotPushEnabled = False
        self.telegramBotPushCheckBox.stateChanged.connect(
            lambda: self.enableTelegramBotPush(self.telegramBotPushCheckBox))
        self.telegramBotSettingsButton.clicked.connect(self.telegramBotSettings)

       
        self.viewGithubRepoButton.clicked.connect(
            lambda: webbrowser.open('https://github.com/winterssy/face_recognition_py'))
        self.contactDeveloperButton.clicked.connect(lambda: webbrowser.open('https://t.me/acankirac'))

        
        self.receiveLogSignal.connect(lambda log: self.logOutput(log))
        self.logOutputThread = threading.Thread(target=self.receiveLog, daemon=True)
        self.logOutputThread.start()

    
    def initDb(self):
        try:
            if not os.path.isfile(self.database):
                raise DatabaseNotFoundError
            if not os.path.isfile(self.trainingData):
                raise TrainingDataNotFoundError

            conn = sqlite3.connect(self.database)
            cursor = conn.cursor()
            cursor.execute('SELECT Count(*) FROM users')
            result = cursor.fetchone()
            dbUserCount = result[0]
        except DatabaseNotFoundError:
            logging.error('The system cannot find the database file{}'.format(self.database))
            self.initDbButton.setIcon(QIcon('./icons/error.png'))
            self.logQueue.put('Error：The database file was not found, you may not have performed face collection')
        except TrainingDataNotFoundError:
            logging.error('The system cannot find the trained face data{}'.format(self.trainingData))
            self.initDbButton.setIcon(QIcon('./icons/error.png'))
            self.logQueue.put('Error：No trained face data files were found, please continue after training')
        except Exception as e:
            logging.error('Error reading database, unable to complete database initialization')
            self.initDbButton.setIcon(QIcon('./icons/error.png'))
            self.logQueue.put('Error：Error reading database, failed to initialize database')
        else:
            cursor.close()
            conn.close()
            if not dbUserCount > 0:
                logging.warning('database is empty')
                self.logQueue.put('warning：The database is empty, the face recognition function is not available')
                self.initDbButton.setIcon(QIcon('./icons/warning.png'))
            else:
                self.logQueue.put('Success：The database status is normal, and the number of users found：{}'.format(dbUserCount))
                self.initDbButton.setIcon(QIcon('./icons/success.png'))
                self.initDbButton.setEnabled(False)
                self.faceRecognizerCheckBox.setToolTip('Face tracking must be turned on first')
                self.faceRecognizerCheckBox.setEnabled(True)

    
    def useExternalCamera(self, useExternalCameraCheckBox):
        if useExternalCameraCheckBox.isChecked():
            self.isExternalCameraUsed = True
        else:
            self.isExternalCameraUsed = False

    
    def startWebcam(self):
        if not self.cap.isOpened():
            if self.isExternalCameraUsed:
                camID = 1
            else:
                camID = 0
            self.cap.open(camID)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            ret, frame = self.cap.read()
            if not ret:
                logging.error('Unable to call computer camera{}'.format(camID))
                self.logQueue.put('Error：Failed to initialize camera')
                self.cap.release()
                self.startWebcamButton.setIcon(QIcon('./icons/error.png'))
            else:
                self.faceProcessingThread.start()  
                self.timer.start(5) 
                self.panalarmThread.start() 
                self.startWebcamButton.setIcon(QIcon('./icons/success.png'))
                self.startWebcamButton.setText('Turn off the camera')

        else:
            text = 'If you turn off the camera, you must restart the program to turn it on again。'
            informativeText = '<b>Whether to continue?</b>'
            ret = CoreUI.callDialog(QMessageBox.Warning, text, informativeText, QMessageBox.Yes | QMessageBox.No,
                                    QMessageBox.No)

            if ret == QMessageBox.Yes:
                self.faceProcessingThread.stop()
                if self.cap.isOpened():
                    if self.timer.isActive():
                        self.timer.stop()
                    self.cap.release()

                self.realTimeCaptureLabel.clear()
                self.realTimeCaptureLabel.setText('<font color=red>Camera is not turned on</font>')
                self.startWebcamButton.setText('Camera is off')
                self.startWebcamButton.setEnabled(False)
                self.startWebcamButton.setIcon(QIcon())

    def updateFrame(self):
        if self.cap.isOpened():
            # ret, frame = self.cap.read()
            # if ret:
            #     self.showImg(frame, self.realTimeCaptureLabel)
            if not self.captureQueue.empty():
                captureData = self.captureQueue.get()
                realTimeFrame = captureData.get('realTimeFrame')
                self.displayImage(realTimeFrame, self.realTimeCaptureLabel)

    def displayImage(self, img, qlabel):
        # BGR -> RGB
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        # default：The image is stored using 8-bit indexes into a colormap， for example：a gray image
        qformat = QImage.Format_Indexed8

        if len(img.shape) == 3:  # rows[0], cols[1], channels[2]
            if img.shape[2] == 4:
                # The image is stored using a 32-bit byte-ordered RGBA format (8-8-8-8)
               
                qformat = QImage.Format_RGBA8888
            else:
                qformat = QImage.Format_RGB888

       

        outImage = QImage(img, img.shape[1], img.shape[0], img.strides[0], qformat)
        qlabel.setPixmap(QPixmap.fromImage(outImage))
        qlabel.setScaledContents(True)  

    def enableBell(self, bellCheckBox):
        if bellCheckBox.isChecked():
            self.isBellEnabled = True
            self.statusBar().showMessage('Device Sound: On')
        else:
            if self.isTelegramBotPushEnabled:
                self.isBellEnabled = False
                self.statusBar().showMessage('Device sound: off')
            else:
                self.logQueue.put('Error：Operation failed, select at least one alarm method')
                self.bellCheckBox.setCheckState(Qt.Unchecked)
                self.bellCheckBox.setChecked(True)
        # print('isBellEnabled：', self.isBellEnabled)

    def enableTelegramBotPush(self, telegramBotPushCheckBox):
        if telegramBotPushCheckBox.isChecked():
            self.isTelegramBotPushEnabled = True
            self.statusBar().showMessage('TelegramBot Push: On')
        else:
            if self.isBellEnabled:
                self.isTelegramBotPushEnabled = False
                self.statusBar().showMessage('TelegramBot push: off')
            else:
                self.logQueue.put('Error：Operation failed, select at least one alarm method')
                self.telegramBotPushCheckBox.setCheckState(Qt.Unchecked)
                self.telegramBotPushCheckBox.setChecked(True)
        # print('isTelegramBotPushEnabled：', self.isTelegramBotPushEnabled)

    
    def telegramBotSettings(self):
        cfg = ConfigParser()
        cfg.read('./config/telegramBot.cfg', encoding='utf-8-sig')
        read_only = cfg.getboolean('telegramBot', 'read_only')
        # read_only = False
        if read_only:
            text = 'Based on security considerations, the system rejected this request.'
            informativeText = '<b>Please contact the device administrator。</b>'
            CoreUI.callDialog(QMessageBox.Critical, text, informativeText, QMessageBox.Ok)
        else:
            token = cfg.get('telegramBot', 'token')
            chat_id = cfg.get('telegramBot', 'chat_id')
            proxy_url = cfg.get('telegramBot', 'proxy_url')
            message = cfg.get('telegramBot', 'message')

            self.telegramBotDialog = TelegramBotDialog()
            self.telegramBotDialog.tokenLineEdit.setText(token)
            self.telegramBotDialog.telegramIDLineEdit.setText(chat_id)
            self.telegramBotDialog.socksLineEdit.setText(proxy_url)
            self.telegramBotDialog.messagePlainTextEdit.setPlainText(message)
            self.telegramBotDialog.exec()

    @staticmethod
    def bellProcess(queue):
        logQueue = queue
        logQueue.put('Info：Device is ringing...')
        #winsound.PlaySound('./alarm.wav', winsound.SND_FILENAME)

    @staticmethod
    def telegramBotPushProcess(queue, img=None):
        logQueue = queue
        cfg = ConfigParser()
        try:
            cfg.read('./config/telegramBot.cfg', encoding='utf-8-sig')

            token = cfg.get('telegramBot', 'token')
            chat_id = cfg.getint('telegramBot', 'chat_id')
            proxy_url = cfg.get('telegramBot', 'proxy_url')
            message = cfg.get('telegramBot', 'message')

            if proxy_url:
                proxy = telegram.utils.request.Request(proxy_url=proxy_url)
                bot = telegram.Bot(token=token, request=proxy)
            else:
                bot = telegram.Bot(token=token)

            bot.send_message(chat_id=chat_id, text=message)

            if img:
                bot.send_photo(chat_id=chat_id, photo=open(img, 'rb'), timeout=10)
        except Exception as e:
            logQueue.put('Error：TelegramBot push failed')
        else:
            logQueue.put('Success：TelegramBot push successfully')

    def recieveAlarm(self):
        while True:
            jobs = []
            # print(self.alarmQueue.qsize())
            if self.alarmQueue.qsize() > self.alarmSignalThreshold:  
                if not os.path.isdir('./unknown'):
                    os.makedirs('./unknown')
                lastAlarmSignal = self.alarmQueue.get()
                timestamp = lastAlarmSignal.get('timestamp')
                img = lastAlarmSignal.get('img')
                cv2.imwrite('./unknown/{}.jpg'.format(timestamp), img)
                logging.info('The alarm signal trigger exceeds the preset count, and the automatic alarm system has been activated')
                self.logQueue.put('Info：The alarm signal trigger exceeds the preset count, and the automatic alarm system has been activated')

                if self.isBellEnabled:
                    p1 = multiprocessing.Process(target=CoreUI.bellProcess, args=(self.logQueue,))
                    p1.start()
                    jobs.append(p1)

                if self.isTelegramBotPushEnabled:
                    if os.path.isfile('./unknown/{}.jpg'.format(timestamp)):
                        img = './unknown/{}.jpg'.format(timestamp)
                    else:
                        img = None
                    p2 = multiprocessing.Process(target=CoreUI.telegramBotPushProcess, args=(self.logQueue, img))
                    p2.start()
                    jobs.append(p2)

                for p in jobs:
                    p.join()

                with self.alarmQueue.mutex:
                    self.alarmQueue.queue.clear()
            else:
                continue

    def receiveLog(self):
        while True:
            data = self.logQueue.get()
            if data:
                self.receiveLogSignal.emit(data)
            else:
                continue

    def logOutput(self, log):
        time = datetime.now().strftime('[%Y/%m/%d %H:%M:%S]')
        log = time + ' ' + log + '\n'

        self.logTextEdit.moveCursor(QTextCursor.End)
        self.logTextEdit.insertPlainText(log)
        self.logTextEdit.ensureCursorVisible()  

    @staticmethod
    def callDialog(icon, text, informativeText, standardButtons, defaultButton=None):
        msg = QMessageBox()
        msg.setWindowIcon(QIcon('./icons/icon.png'))
        msg.setWindowTitle('OpenCV Face Recognition System - Core')
        msg.setIcon(icon)
        msg.setText(text)
        msg.setInformativeText(informativeText)
        msg.setStandardButtons(standardButtons)
        if defaultButton:
            msg.setDefaultButton(defaultButton)
        return msg.exec()

    def closeEvent(self, event):
        if self.faceProcessingThread.isRunning:
            self.faceProcessingThread.stop()
        if self.timer.isActive():
            self.timer.stop()
        if self.cap.isOpened():
            self.cap.release()
        event.accept()


class TelegramBotDialog(QDialog):
    def __init__(self):
        super(TelegramBotDialog, self).__init__()
        loadUi('./ui/TelegramBotDialog.ui', self)
        self.setWindowIcon(QIcon('./icons/icon.png'))
        self.setFixedSize(550, 358)

        chat_id_regx = QRegExp('^\d+$')
        chat_id_validator = QRegExpValidator(chat_id_regx, self.telegramIDLineEdit)
        self.telegramIDLineEdit.setValidator(chat_id_validator)

        self.okButton.clicked.connect(self.telegramBotSettings)

    def telegramBotSettings(self):
        token = self.tokenLineEdit.text().strip()
        chat_id = self.telegramIDLineEdit.text().strip()
        proxy_url = self.socksLineEdit.text().strip()
        message = self.messagePlainTextEdit.toPlainText().strip()

        if not (token and chat_id and message):
            self.okButton.setIcon(QIcon('./icons/error.png'))
            CoreUI.logQueue.put('Error：API Token、Telegram ID and message content are required')
        else:
            ret = self.telegramBotTest(token, proxy_url)
            if ret:
                cfg_file = './config/telegramBot.cfg'
                cfg = ConfigParser()
                cfg.read(cfg_file, encoding='utf-8-sig')

                cfg.set('telegramBot', 'token', token)
                cfg.set('telegramBot', 'chat_id', chat_id)
                cfg.set('telegramBot', 'proxy_url', proxy_url)
                cfg.set('telegramBot', 'message', message)

                try:
                    with open(cfg_file, 'w', encoding='utf-8') as file:
                        cfg.write(file)
                except:
                    logging.error('An exception occurred when writing the telegramBot configuration file')
                    CoreUI.logQueue.put('Error：An exception occurred while writing the configuration file, the update failed')
                else:
                    CoreUI.logQueue.put('Success：The test passed, the system has updated the TelegramBot configuration')
                    self.close()
            else:
                CoreUI.logQueue.put('Error：Test failed, unable to update TelegramBot configuration')

    def telegramBotTest(self, token, proxy_url):
        try:
            if proxy_url:
                proxy = telegram.utils.request.Request(proxy_url=proxy_url)
                bot = telegram.Bot(token=token, request=proxy)
            else:
                bot = telegram.Bot(token=token)
            bot.get_me()
        except Exception as e:
            return False
        else:
            return True


class FaceProcessingThread(QThread):
    def __init__(self):
        super(FaceProcessingThread, self).__init__()
        self.isRunning = True

        self.isFaceTrackerEnabled = True
        self.isFaceRecognizerEnabled = False
        self.isPanalarmEnabled = True

        self.isDebugMode = False
        self.confidenceThreshold = 50
        self.autoAlarmThreshold = 65

        self.isEqualizeHistEnabled = False

    def enableFaceTracker(self, coreUI):
        if coreUI.faceTrackerCheckBox.isChecked():
            self.isFaceTrackerEnabled = True
            coreUI.statusBar().showMessage('Face Tracking: On')
        else:
            self.isFaceTrackerEnabled = False
            coreUI.statusBar().showMessage('Face Tracking: Off')

    def enableFaceRecognizer(self, coreUI):
        if coreUI.faceRecognizerCheckBox.isChecked():
            if self.isFaceTrackerEnabled:
                self.isFaceRecognizerEnabled = True
                coreUI.statusBar().showMessage('Face Recognition: On')
            else:
                CoreUI.logQueue.put('Error：Operation failed, please enable face tracking first')
                coreUI.faceRecognizerCheckBox.setCheckState(Qt.Unchecked)
                coreUI.faceRecognizerCheckBox.setChecked(False)
        else:
            self.isFaceRecognizerEnabled = False
            coreUI.statusBar().showMessage('Face Recognition: Off')

    def enablePanalarm(self, coreUI):
        if coreUI.panalarmCheckBox.isChecked():
            self.isPanalarmEnabled = True
            coreUI.statusBar().showMessage('Alarm system: on')
        else:
            self.isPanalarmEnabled = False
            coreUI.statusBar().showMessage('Alarm system: off')

    def enableDebug(self, coreUI):
        if coreUI.debugCheckBox.isChecked():
            self.isDebugMode = True
            coreUI.statusBar().showMessage('Debug Mode: On')
        else:
            self.isDebugMode = False
            coreUI.statusBar().showMessage('Debug mode: Off')

    def setConfidenceThreshold(self, coreUI):
        if self.isDebugMode:
            self.confidenceThreshold = coreUI.confidenceThresholdSlider.value()
            coreUI.statusBar().showMessage('Confidence Threshold：{}'.format(self.confidenceThreshold))

    def setAutoAlarmThreshold(self, coreUI):
        if self.isDebugMode:
            self.autoAlarmThreshold = coreUI.autoAlarmThresholdSlider.value()
            coreUI.statusBar().showMessage('Automatic alarm threshold：{}'.format(self.autoAlarmThreshold))

    def enableEqualizeHist(self, coreUI):
        if coreUI.equalizeHistCheckBox.isChecked():
            self.isEqualizeHistEnabled = True
            coreUI.statusBar().showMessage('Histogram Equalization: On')
        else:
            self.isEqualizeHistEnabled = False
            coreUI.statusBar().showMessage('Histogram equalization: off')

    def run(self):
        faceCascade = cv2.CascadeClassifier('./haarcascades/haarcascade_frontalface_default.xml')

        frameCounter = 0
        currentFaceID = 0

        faceTrackers = {}

        isTrainingDataLoaded = False
        isDbConnected = False

        while self.isRunning:
            if CoreUI.cap.isOpened():
                ret, frame = CoreUI.cap.read()
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                if self.isEqualizeHistEnabled:
                    gray = cv2.equalizeHist(gray)
                faces = faceCascade.detectMultiScale(gray, 1.3, 5, minSize=(90, 90))

                if not isTrainingDataLoaded and os.path.isfile(CoreUI.trainingData):
                    recognizer = cv2.face.LBPHFaceRecognizer_create()
                    recognizer.read(CoreUI.trainingData)
                    isTrainingDataLoaded = True
                if not isDbConnected and os.path.isfile(CoreUI.database):
                    conn = sqlite3.connect(CoreUI.database)
                    cursor = conn.cursor()
                    isDbConnected = True

                captureData = {}
                realTimeFrame = frame.copy()
                alarmSignal = {}

                
                if self.isFaceTrackerEnabled:

                    fidsToDelete = []

                    for fid in faceTrackers.keys():
                        trackingQuality = faceTrackers[fid].update(realTimeFrame)
                        if trackingQuality < 7:
                            fidsToDelete.append(fid)

                    for fid in fidsToDelete:
                        faceTrackers.pop(fid, None)

                    for (_x, _y, _w, _h) in faces:
                        isKnown = False

                        if self.isFaceRecognizerEnabled:
                            cv2.rectangle(realTimeFrame, (_x, _y), (_x + _w, _y + _h), (232, 138, 30), 2)
                            face_id, confidence = recognizer.predict(gray[_y:_y + _h, _x:_x + _w])
                            logging.debug('face_id：{}，confidence：{}'.format(face_id, confidence))

                            if self.isDebugMode:
                                CoreUI.logQueue.put('Debug -> face_id：{}，confidence：{}'.format(face_id, confidence))

                            try:
                                cursor.execute("SELECT * FROM users WHERE face_id=?", (face_id,))
                                result = cursor.fetchall()
                                if result:
                                    en_name = result[0][3]
                                else:
                                    raise Exception
                            except Exception as e:
                                logging.error('The database is read abnormally, and the system cannot obtain the Face ID as{}identity information'.format(face_id))
                                CoreUI.logQueue.put('Error：The database is read abnormally, and the system cannot obtain the Face ID as{}identity information'.format(face_id))
                                en_name = ''

                            if confidence < self.confidenceThreshold:
                                isKnown = True
                                cv2.putText(realTimeFrame, en_name, (_x - 5, _y - 10), cv2.FONT_HERSHEY_SIMPLEX, 1,
                                            (0, 97, 255), 2)
                            else:
                                cv2.putText(realTimeFrame, 'unknown', (_x - 5, _y - 10), cv2.FONT_HERSHEY_SIMPLEX, 1,
                                            (0, 0, 255), 2)
                                if confidence > self.autoAlarmThreshold:
                                    if self.isPanalarmEnabled:
                                        alarmSignal['timestamp'] = datetime.now().strftime('%Y%m%d%H%M%S')
                                        alarmSignal['img'] = realTimeFrame
                                        CoreUI.alarmQueue.put(alarmSignal)
                                        logging.info('The system has issued an alarm signal')

                        frameCounter += 1

                        if frameCounter % 10 == 0:
                            
                            x = int(_x)
                            y = int(_y)
                            w = int(_w)
                            h = int(_h)

                            x_bar = x + 0.5 * w
                            y_bar = y + 0.5 * h

                            matchedFid = None

                            for fid in faceTrackers.keys():
                                tracked_position = faceTrackers[fid].get_position()
                                t_x = int(tracked_position.left())
                                t_y = int(tracked_position.top())
                                t_w = int(tracked_position.width())
                                t_h = int(tracked_position.height())

                                t_x_bar = t_x + 0.5 * t_w
                                t_y_bar = t_y + 0.5 * t_h

                                
                                if ((t_x <= x_bar <= (t_x + t_w)) and (t_y <= y_bar <= (t_y + t_h)) and
                                        (x <= t_x_bar <= (x + w)) and (y <= t_y_bar <= (y + h))):
                                    matchedFid = fid

                            if not isKnown and matchedFid is None:
                                tracker = dlib.correlation_tracker()
                                tracker.start_track(realTimeFrame, dlib.rectangle(x - 5, y - 10, x + w + 5, y + h + 10))
                                faceTrackers[currentFaceID] = tracker
                                currentFaceID += 1

                    for fid in faceTrackers.keys():
                        tracked_position = faceTrackers[fid].get_position()

                        t_x = int(tracked_position.left())
                        t_y = int(tracked_position.top())
                        t_w = int(tracked_position.width())
                        t_h = int(tracked_position.height())

                        cv2.rectangle(realTimeFrame, (t_x, t_y), (t_x + t_w, t_y + t_h), (0, 0, 255), 2)
                        cv2.putText(realTimeFrame, 'Tracking...', (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 255),
                                    2)

                captureData['originFrame'] = frame
                captureData['realTimeFrame'] = realTimeFrame
                CoreUI.captureQueue.put(captureData)

            else:
                continue

    def stop(self):
        self.isRunning = False
        self.quit()
        self.wait()


if __name__ == '__main__':
    logging.config.fileConfig('./config/logging.cfg')
    app = QApplication(sys.argv)
    window = CoreUI()
    window.show()
    sys.exit(app.exec())
