# created by KRC
# KRC Support You


import cv2

from PyQt5.QtCore import QTimer, QRegExp, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap, QIcon, QRegExpValidator, QTextCursor
from PyQt5.QtWidgets import QDialog, QApplication, QWidget, QMessageBox
from PyQt5.uic import loadUi

import logging
import logging.config
import queue
import threading
import sqlite3
import os
import sys

from datetime import datetime


class OperationCancel(Exception):
    pass


class RecordDisturbance(Exception):
    pass


class DataRecordUI(QWidget):
    receiveLogSignal = pyqtSignal(str)

    def __init__(self):
        super(DataRecordUI, self).__init__()
        loadUi('./ui/DataRecord.ui', self)
        self.setWindowIcon(QIcon('./icons/icon.png'))
        self.setFixedSize(1200, 670)

        self.cap = cv2.VideoCapture(0)
        self.faceCascade = cv2.CascadeClassifier('./haarcascades/haarcascade_frontalface_default.xml')

        self.logQueue = queue.Queue()  

        self.isExternalCameraUsed = False
        self.useExternalCameraCheckBox.stateChanged.connect(
            lambda: self.useExternalCamera(self.useExternalCameraCheckBox))
        self.startWebcamButton.toggled.connect(self.startWebcam)
        self.startWebcamButton.setCheckable(True)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.updateFrame)

        self.isFaceDetectEnabled = False
        self.enableFaceDetectButton.toggled.connect(self.enableFaceDetect)
        self.enableFaceDetectButton.setCheckable(True)

        self.database = './FaceBase.db'
        self.datasets = './datasets'
        self.isDbReady = False
        self.initDbButton.setIcon(QIcon('./icons/warning.png'))
        self.initDbButton.clicked.connect(self.initDb)

        self.isUserInfoReady = False
        self.userInfo = {'stu_id': '', 'cn_name': '', 'en_name': ''}
        self.addOrUpdateUserInfoButton.clicked.connect(self.addOrUpdateUserInfo)
        self.migrateToDbButton.clicked.connect(self.migrateToDb)

        self.startFaceRecordButton.clicked.connect(lambda: self.startFaceRecord(self.startFaceRecordButton))
        # self.startFaceRecordButton.setCheckable(True)
        self.faceRecordCount = 0
        self.minFaceRecordCount = 100
        self.isFaceDataReady = False
        self.isFaceRecordEnabled = False
        self.enableFaceRecordButton.clicked.connect(self.enableFaceRecord)

        self.receiveLogSignal.connect(lambda log: self.logOutput(log))
        self.logOutputThread = threading.Thread(target=self.receiveLog, daemon=True)
        self.logOutputThread.start()

    def useExternalCamera(self, useExternalCameraCheckBox):
        if useExternalCameraCheckBox.isChecked():
            self.isExternalCameraUsed = True
        else:
            self.isExternalCameraUsed = False

    def startWebcam(self, status):
        if status:
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
                self.startWebcamButton.setChecked(False)
            else:
                self.startWebcamButton.setText('Turn off the camera')
                self.enableFaceDetectButton.setEnabled(True)
                self.timer.start(5)
                self.startWebcamButton.setIcon(QIcon('./icons/success.png'))
        else:
            if self.cap.isOpened():
                if self.timer.isActive():
                    self.timer.stop()
                self.cap.release()
                self.faceDetectCaptureLabel.clear()
                self.faceDetectCaptureLabel.setText('<font color=red>Camera is not turned on</font>')
                self.startWebcamButton.setText('Turn on the camera')
                self.enableFaceDetectButton.setEnabled(False)
                self.startWebcamButton.setIcon(QIcon())

    def enableFaceDetect(self, status):
        if self.cap.isOpened():
            if status:
                self.enableFaceDetectButton.setText('Turn off face detection')
                self.isFaceDetectEnabled = True
            else:
                self.enableFaceDetectButton.setText('Turn on face detection')
                self.isFaceDetectEnabled = False

    def enableFaceRecord(self):
        if not self.isFaceRecordEnabled:
            self.isFaceRecordEnabled = True

    def startFaceRecord(self, startFaceRecordButton):
        if startFaceRecordButton.text() == 'Start collecting face data':
            if self.isFaceDetectEnabled:
                if self.isUserInfoReady:
                    self.addOrUpdateUserInfoButton.setEnabled(False)
                    if not self.enableFaceRecordButton.isEnabled():
                        self.enableFaceRecordButton.setEnabled(True)
                    self.enableFaceRecordButton.setIcon(QIcon())
                    self.startFaceRecordButton.setIcon(QIcon('./icons/success.png'))
                    self.startFaceRecordButton.setText('End the current face collection')
                else:
                    self.startFaceRecordButton.setIcon(QIcon('./icons/error.png'))
                    self.startFaceRecordButton.setChecked(False)
                    self.logQueue.put('Error：The operation failed, the system did not detect valid user information')
            else:
                self.startFaceRecordButton.setIcon(QIcon('./icons/error.png'))
                self.logQueue.put('Error：Operation failed, please enable face detection')
        else:
            if self.faceRecordCount < self.minFaceRecordCount:
                text = 'The system currently collects <font color=blue>{}</font> Frame images, too little collected data will lead to larger recognition errors.'.format(self.faceRecordCount)
                informativeText = '<b>Please collect at least <font color=red>{}</font> frame image.</b>'.format(self.minFaceRecordCount)
                DataRecordUI.callDialog(QMessageBox.Information, text, informativeText, QMessageBox.Ok)

            else:
                text = 'The system currently collects <font color=blue>{}</font> Frame image, continue to collect can improve the recognition accuracy。'.format(self.faceRecordCount)
                informativeText = '<b>Are you sure to end the current face collection?</b>'
                ret = DataRecordUI.callDialog(QMessageBox.Question, text, informativeText,
                                              QMessageBox.Yes | QMessageBox.No,
                                              QMessageBox.No)

                if ret == QMessageBox.Yes:
                    self.isFaceDataReady = True
                    if self.isFaceRecordEnabled:
                        self.isFaceRecordEnabled = False
                    self.enableFaceRecordButton.setEnabled(False)
                    self.enableFaceRecordButton.setIcon(QIcon())
                    self.startFaceRecordButton.setText('Start collecting face data')
                    self.startFaceRecordButton.setEnabled(False)
                    self.startFaceRecordButton.setIcon(QIcon())
                    self.migrateToDbButton.setEnabled(True)

    def updateFrame(self):
        ret, frame = self.cap.read()
        # self.image = cv2.flip(self.image, 1)
        if ret:
            self.displayImage(frame)

            if self.isFaceDetectEnabled:
                detected_frame = self.detectFace(frame)
                self.displayImage(detected_frame)
            else:
                self.displayImage(frame)

    def detectFace(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.faceCascade.detectMultiScale(gray, 1.3, 5, minSize=(90, 90))

        stu_id = self.userInfo.get('stu_id')

        for (x, y, w, h) in faces:
            if self.isFaceRecordEnabled:
                try:
                    if not os.path.exists('{}/stu_{}'.format(self.datasets, stu_id)):
                        os.makedirs('{}/stu_{}'.format(self.datasets, stu_id))
                    if len(faces) > 1:
                        raise RecordDisturbance

                    cv2.imwrite('{}/stu_{}/img.{}.jpg'.format(self.datasets, stu_id, self.faceRecordCount + 1),
                                gray[y - 20:y + h + 20, x - 20:x + w + 20])
                except RecordDisturbance:
                    self.isFaceRecordEnabled = False
                    logging.error('Multiple faces or environmental distractions detected')
                    self.logQueue.put('Warning：Multiple faces or environmental disturbances detected, please fix the problem and continue')
                    self.enableFaceRecordButton.setIcon(QIcon('./icons/warning.png'))
                    continue
                except Exception as e:
                    logging.error('An exception occurred while writing the face image file to the computer')
                    self.enableFaceRecordButton.setIcon(QIcon('./icons/error.png'))
                    self.logQueue.put('Error：Failed to save face image, failed to capture current capture frame')
                else:
                    self.enableFaceRecordButton.setIcon(QIcon('./icons/success.png'))
                    self.faceRecordCount = self.faceRecordCount + 1
                    self.isFaceRecordEnabled = False
                    self.faceRecordCountLcdNum.display(self.faceRecordCount)
            cv2.rectangle(frame, (x - 5, y - 10), (x + w + 5, y + h + 10), (0, 0, 255), 2)

        return frame

    def displayImage(self, img):
        # BGR -> RGB
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        qformat = QImage.Format_Indexed8

        if len(img.shape) == 3:  # rows[0], cols[1], channels[2]
            if img.shape[2] == 4:
               
                qformat = QImage.Format_RGBA8888
            else:
                qformat = QImage.Format_RGB888

        

        outImage = QImage(img, img.shape[1], img.shape[0], img.strides[0], qformat)
        self.faceDetectCaptureLabel.setPixmap(QPixmap.fromImage(outImage))
        self.faceDetectCaptureLabel.setScaledContents(True)

    def initDb(self):
        conn = sqlite3.connect(self.database)
        cursor = conn.cursor()
        try:
            if not os.path.isdir(self.datasets):
                os.makedirs(self.datasets)

            cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                              stu_id VARCHAR(12) PRIMARY KEY NOT NULL,
                              face_id INTEGER DEFAULT -1,
                              cn_name VARCHAR(10) NOT NULL,
                              en_name VARCHAR(16) NOT NULL,
                              created_time DATE DEFAULT (date('now','localtime'))
                              )
                          ''')
            cursor.execute('SELECT Count(*) FROM users')
            result = cursor.fetchone()
            dbUserCount = result[0]
        except Exception as e:
            logging.error('Error reading database, unable to complete database initialization')
            self.isDbReady = False
            self.initDbButton.setIcon(QIcon('./icons/error.png'))
            self.logQueue.put('Error：Failed to initialize database')
        else:
            self.isDbReady = True
            self.dbUserCountLcdNum.display(dbUserCount)
            self.logQueue.put('Success：Database initialization is complete')
            self.initDbButton.setIcon(QIcon('./icons/success.png'))
            self.initDbButton.setEnabled(False)
            self.addOrUpdateUserInfoButton.setEnabled(True)
        finally:
            cursor.close()
            conn.commit()
            conn.close()

    def addOrUpdateUserInfo(self):
        self.userInfoDialog = UserInfoDialog()

        stu_id, cn_name, en_name = self.userInfo.get('stu_id'), self.userInfo.get('cn_name'), self.userInfo.get(
            'en_name')
        self.userInfoDialog.stuIDLineEdit.setText(stu_id)
        self.userInfoDialog.cnNameLineEdit.setText(cn_name)
        self.userInfoDialog.enNameLineEdit.setText(en_name)

        self.userInfoDialog.okButton.clicked.connect(self.checkToApplyUserInfo)
        self.userInfoDialog.exec()

    def checkToApplyUserInfo(self):
        if not (self.userInfoDialog.stuIDLineEdit.hasAcceptableInput() and
                self.userInfoDialog.cnNameLineEdit.hasAcceptableInput() and
                self.userInfoDialog.enNameLineEdit.hasAcceptableInput()):
            self.userInfoDialog.msgLabel.setText('<font color=red>Your input is incorrect and the submission failed, please check and try again!</font>')
        else:
            self.userInfo['stu_id'] = self.userInfoDialog.stuIDLineEdit.text().strip()
            self.userInfo['cn_name'] = self.userInfoDialog.cnNameLineEdit.text().strip()
            self.userInfo['en_name'] = self.userInfoDialog.enNameLineEdit.text().strip()

            stu_id, cn_name, en_name = self.userInfo.get('stu_id'), self.userInfo.get('cn_name'), self.userInfo.get(
                'en_name')
            self.stuIDLineEdit.setText(stu_id)
            self.cnNameLineEdit.setText(cn_name)
            self.enNameLineEdit.setText(en_name)

            self.isUserInfoReady = True
            if not self.startFaceRecordButton.isEnabled():
                self.startFaceRecordButton.setEnabled(True)
            self.migrateToDbButton.setIcon(QIcon())

            self.userInfoDialog.close()

    def migrateToDb(self):
        if self.isFaceDataReady:
            stu_id, cn_name, en_name = self.userInfo.get('stu_id'), self.userInfo.get('cn_name'), self.userInfo.get(
                'en_name')
            conn = sqlite3.connect(self.database)
            cursor = conn.cursor()

            try:
                cursor.execute('SELECT * FROM users WHERE stu_id=?', (stu_id,))
                if cursor.fetchall():
                    text = 'The database already exists with the student ID of <font color=blue>{}</font> user records.'.format(stu_id)
                    informativeText = '<b>Override?</b>'
                    ret = DataRecordUI.callDialog(QMessageBox.Warning, text, informativeText,
                                                  QMessageBox.Yes | QMessageBox.No)

                    if ret == QMessageBox.Yes:
                        cursor.execute('UPDATE users SET cn_name=?, en_name=? WHERE stu_id=?',
                                       (cn_name, en_name, stu_id,))
                    else:
                        raise OperationCancel  
                else:
                    cursor.execute('INSERT INTO users (stu_id, cn_name, en_name) VALUES (?, ?, ?)',
                                   (stu_id, cn_name, en_name,))

                cursor.execute('SELECT Count(*) FROM users')
                result = cursor.fetchone()
                dbUserCount = result[0]
            except OperationCancel:
                pass
            except Exception as e:
                logging.error('Read and write database exception, unable to insert/update records to database')
                self.migrateToDbButton.setIcon(QIcon('./icons/error.png'))
                self.logQueue.put('Error：Read and write database exception, synchronization failed')
            else:
                text = '<font color=blue>{}</font> Added/updated to database.'.format(stu_id)
                informativeText = '<b><font color=blue>{}</font> The collection of face data has been completed!</b>'.format(cn_name)
                DataRecordUI.callDialog(QMessageBox.Information, text, informativeText, QMessageBox.Ok)

                for key in self.userInfo.keys():
                    self.userInfo[key] = ''
                self.isUserInfoReady = False

                self.faceRecordCount = 0
                self.isFaceDataReady = False
                self.faceRecordCountLcdNum.display(self.faceRecordCount)
                self.dbUserCountLcdNum.display(dbUserCount)

                self.stuIDLineEdit.clear()
                self.cnNameLineEdit.clear()
                self.enNameLineEdit.clear()
                self.migrateToDbButton.setIcon(QIcon('./icons/success.png'))

                self.addOrUpdateUserInfoButton.setEnabled(True)
                self.migrateToDbButton.setEnabled(False)

            finally:
                cursor.close()
                conn.commit()
                conn.close()
        else:
            self.logQueue.put('Error：The operation failed, you have not completed the face data collection')
            self.migrateToDbButton.setIcon(QIcon('./icons/error.png'))

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
        msg.setWindowTitle('OpenCV Face Recognition System - DataRecord')
        msg.setIcon(icon)
        msg.setText(text)
        msg.setInformativeText(informativeText)
        msg.setStandardButtons(standardButtons)
        if defaultButton:
            msg.setDefaultButton(defaultButton)
        return msg.exec()

    def closeEvent(self, event):
        if self.timer.isActive():
            self.timer.stop()
        if self.cap.isOpened():
            self.cap.release()
        event.accept()


class UserInfoDialog(QDialog):
    def __init__(self):
        super(UserInfoDialog, self).__init__()
        loadUi('./ui/UserInfoDialog.ui', self)
        self.setWindowIcon(QIcon('./icons/icon.png'))
        self.setFixedSize(425, 300)

        stu_id_regx = QRegExp('^[0-9]{12}$')
        stu_id_validator = QRegExpValidator(stu_id_regx, self.stuIDLineEdit)
        self.stuIDLineEdit.setValidator(stu_id_validator)

        cn_name_regx = QRegExp('^[ A-Za-z]{1,16}$')
        cn_name_validator = QRegExpValidator(cn_name_regx, self.cnNameLineEdit)
        self.cnNameLineEdit.setValidator(cn_name_validator)

        en_name_regx = QRegExp('^[ A-Za-z]{1,16}$')
        en_name_validator = QRegExpValidator(en_name_regx, self.enNameLineEdit)
        self.enNameLineEdit.setValidator(en_name_validator)


if __name__ == '__main__':
    logging.config.fileConfig('./config/logging.cfg')
    app = QApplication(sys.argv)
    window = DataRecordUI()
    window.show()
    sys.exit(app.exec())
