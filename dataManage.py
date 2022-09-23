# created by KRC
# KRC Support You

import cv2
import numpy as np

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QIcon, QTextCursor
from PyQt5.QtWidgets import QApplication, QWidget, QMessageBox, QTableWidgetItem, QAbstractItemView
from PyQt5.uic import loadUi

import logging
import logging.config
import os
import shutil
import sqlite3
import sys
import threading
import multiprocessing

from datetime import datetime


class RecordNotFound(Exception):
    pass


class DataManageUI(QWidget):
    logQueue = multiprocessing.Queue()  
    receiveLogSignal = pyqtSignal(str)  

    def __init__(self):
        super(DataManageUI, self).__init__()
        loadUi('./ui/DataManage.ui', self)
        self.setWindowIcon(QIcon('./icons/icon.png'))
        self.setFixedSize(1080, 640)

        
        self.tableWidget.setEditTriggers(QAbstractItemView.NoEditTriggers)

        
        self.database = './FaceBase.db'
        self.datasets = './datasets'
        self.isDbReady = False
        self.initDbButton.clicked.connect(self.initDb)

        self.queryUserButton.clicked.connect(self.queryUser)
        self.deleteUserButton.clicked.connect(self.deleteUser)

        self.isEqualizeHistEnabled = False
        self.equalizeHistCheckBox.stateChanged.connect(
            lambda: self.enableEqualizeHist(self.equalizeHistCheckBox))

        self.trainButton.clicked.connect(self.train)

        self.receiveLogSignal.connect(lambda log: self.logOutput(log))
        self.logOutputThread = threading.Thread(target=self.receiveLog, daemon=True)
        self.logOutputThread.start()

    def enableEqualizeHist(self, equalizeHistCheckBox):
        if equalizeHistCheckBox.isChecked():
            self.isEqualizeHistEnabled = True
        else:
            self.isEqualizeHistEnabled = False

    def initDb(self):
        while self.tableWidget.rowCount() > 0:
            self.tableWidget.removeRow(0)
        try:
            if not os.path.isfile(self.database):
                raise FileNotFoundError

            conn = sqlite3.connect(self.database)
            cursor = conn.cursor()

            res = cursor.execute('SELECT * FROM users')
            for row_index, row_data in enumerate(res):
                self.tableWidget.insertRow(row_index)
                for col_index, col_data in enumerate(row_data):
                    self.tableWidget.setItem(row_index, col_index, QTableWidgetItem(str(col_data)))
            cursor.execute('SELECT Count(*) FROM users')
            result = cursor.fetchone()
            dbUserCount = result[0]
        except FileNotFoundError:
            logging.error('The system cannot find the database file{}'.format(self.database))
            self.isDbReady = False
            self.initDbButton.setIcon(QIcon('./icons/error.png'))
            self.logQueue.put('Error：The database file was not found, you may not have performed face collection')
        except Exception:
            logging.error('Error reading database, unable to complete database initialization')
            self.isDbReady = False
            self.initDbButton.setIcon(QIcon('./icons/error.png'))
            self.logQueue.put('Error：Read database exception, failed to initialize/refresh database')
        else:
            cursor.close()
            conn.close()

            self.dbUserCountLcdNum.display(dbUserCount)
            if not self.isDbReady:
                self.isDbReady = True
                self.logQueue.put('Success：The database initialization is completed, and the number of users is found:{}'.format(dbUserCount))
                self.initDbButton.setText('Refresh the database')
                self.initDbButton.setIcon(QIcon('./icons/success.png'))
                self.trainButton.setToolTip('')
                self.trainButton.setEnabled(True)
                self.queryUserButton.setToolTip('')
                self.queryUserButton.setEnabled(True)
            else:
                self.logQueue.put('Success：The database was refreshed successfully, and the number of users was found:{}'.format(dbUserCount))

    def queryUser(self):
        stu_id = self.queryUserLineEdit.text().strip()
        conn = sqlite3.connect(self.database)
        cursor = conn.cursor()

        try:
            cursor.execute('SELECT * FROM users WHERE stu_id=?', (stu_id,))
            ret = cursor.fetchall()
            if not ret:
                raise RecordNotFound
            face_id = ret[0][1]
            cn_name = ret[0][2]
        except RecordNotFound:
            self.queryUserButton.setIcon(QIcon('./icons/error.png'))
            self.queryResultLabel.setText('<font color=red>Error：This user does not exist</font>')
        except Exception as e:
            logging.error('Reading database exception, unable to query{}user information'.format(stu_id))
            self.queryResultLabel.clear()
            self.queryUserButton.setIcon(QIcon('./icons/error.png'))
            self.logQueue.put('Error：Read database exception, query failed')
        else:
            self.queryResultLabel.clear()
            self.queryUserButton.setIcon(QIcon('./icons/success.png'))
            self.stuIDLineEdit.setText(stu_id)
            self.cnNameLineEdit.setText(cn_name)
            self.faceIDLineEdit.setText(str(face_id))
            self.deleteUserButton.setEnabled(True)
        finally:
            cursor.close()
            conn.close()

    def deleteUser(self):
        text = 'Delete the user from the database and delete the corresponding face data，<font color=red>This operation is irreversible！</font>'
        informativeText = '<b>Whether to continue？</b>'
        ret = DataManageUI.callDialog(QMessageBox.Warning, text, informativeText, QMessageBox.Yes | QMessageBox.No,
                                      QMessageBox.No)

        if ret == QMessageBox.Yes:
            stu_id = self.stuIDLineEdit.text()
            conn = sqlite3.connect(self.database)
            cursor = conn.cursor()

            try:
                cursor.execute('DELETE FROM users WHERE stu_id=?', (stu_id,))
            except Exception as e:
                cursor.close()
                logging.error('Cant delete from database{}'.format(stu_id))
                self.deleteUserButton.setIcon(QIcon('./icons/error.png'))
                self.logQueue.put('Error：Read and write database exception, delete failed')
            else:
                cursor.close()
                conn.commit()
                if os.path.exists('{}/stu_{}'.format(self.datasets, stu_id)):
                    try:
                        shutil.rmtree('{}/stu_{}'.format(self.datasets, stu_id))
                    except Exception as e:
                        logging.error('The system cannot delete {}/stu_{}'.format(self.datasets, stu_id))
                        self.logQueue.put('Error：Failed to delete face data, please delete it manually{}/stu_{}Table of contents'.format(self.datasets, stu_id))

                text = 'You have successfully deleted the student ID of <font color=blue>{}</font> user records of。'.format(stu_id)
                informativeText = '<b>Please retrain face data in the right menu。</b>'
                DataManageUI.callDialog(QMessageBox.Information, text, informativeText, QMessageBox.Ok)

                self.stuIDLineEdit.clear()
                self.cnNameLineEdit.clear()
                self.faceIDLineEdit.clear()
                self.initDb()
                self.deleteUserButton.setIcon(QIcon('./icons/success.png'))
                self.deleteUserButton.setEnabled(False)
                self.queryUserButton.setIcon(QIcon())
            finally:
                conn.close()

    def detectFace(self, img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if self.isEqualizeHistEnabled:
            gray = cv2.equalizeHist(gray)
        face_cascade = cv2.CascadeClassifier('./haarcascades/haarcascade_frontalface_default.xml')
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.3, minNeighbors=5, minSize=(90, 90))

        if (len(faces) == 0):
            return None, None
        (x, y, w, h) = faces[0]
        return gray[y:y + w, x:x + h], faces[0]

    def prepareTrainingData(self, data_folder_path):
        dirs = os.listdir(data_folder_path)
        faces = []
        labels = []

        face_id = 1
        conn = sqlite3.connect(self.database)
        cursor = conn.cursor()

        for dir_name in dirs:
            if not dir_name.startswith('stu_'):
                continue
            stu_id = dir_name.replace('stu_', '')
            try:
                cursor.execute('SELECT * FROM users WHERE stu_id=?', (stu_id,))
                ret = cursor.fetchall()
                if not ret:
                    raise RecordNotFound
                cursor.execute('UPDATE users SET face_id=? WHERE stu_id=?', (face_id, stu_id,))
            except RecordNotFound:
                logging.warning('The  ID is not found in the database{}user records of'.format(stu_id))
                self.logQueue.put('Found that the id is{}face data of , but the corresponding record could not be found in the database, it has been ignored'.format(stu_id))
                continue
            subject_dir_path = data_folder_path + '/' + dir_name
            subject_images_names = os.listdir(subject_dir_path)
            for image_name in subject_images_names:
                if image_name.startswith('.'):
                    continue
                image_path = subject_dir_path + '/' + image_name
                image = cv2.imread(image_path)
                face, rect = self.detectFace(image)
                if face is not None:
                    faces.append(face)
                    labels.append(face_id)
            face_id = face_id + 1

        cursor.close()
        conn.commit()
        conn.close()

        return faces, labels

   
    def train(self):
        try:
            if not os.path.isdir(self.datasets):
                raise FileNotFoundError

            text = 'The system will start training face data, the interface will pause for a while, and a prompt will pop up after completion。'
            informativeText = '<b>Do not perform other operations during the training process. Do you want to continue?</b>'
            ret = DataManageUI.callDialog(QMessageBox.Question, text, informativeText,
                                          QMessageBox.Yes | QMessageBox.No,
                                          QMessageBox.No)
            if ret == QMessageBox.Yes:
                face_recognizer = cv2.face.LBPHFaceRecognizer_create()
                if not os.path.exists('./recognizer'):
                    os.makedirs('./recognizer')
            faces, labels = self.prepareTrainingData(self.datasets)
            face_recognizer.train(faces, np.array(labels))
            face_recognizer.save('./recognizer/trainingData.yml')
        except FileNotFoundError:
            logging.error('The system cannot find the face data directory{}'.format(self.datasets))
            self.trainButton.setIcon(QIcon('./icons/error.png'))
            self.logQueue.put('Face data directory not found{}，You may not be collecting faces'.format(self.datasets))
        except Exception as e:
            logging.error('An exception occurred in traversing the face database, and the training face data failed')
            self.trainButton.setIcon(QIcon('./icons/error.png'))
            self.logQueue.put('Error：An exception occurs when traversing the face database, and the training fails')
        else:
            text = '<font color=green><b>Success!</b></font> system has been generated./recognizer/trainingData.yml'
            informativeText = '<b>Face data training completed！</b>'
            DataManageUI.callDialog(QMessageBox.Information, text, informativeText, QMessageBox.Ok)
            self.trainButton.setIcon(QIcon('./icons/success.png'))
            self.logQueue.put('Success：Face data training completed')
            self.initDb()

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
        msg.setWindowTitle('OpenCV Face Recognition System - DataManage')
        msg.setIcon(icon)
        msg.setText(text)
        msg.setInformativeText(informativeText)
        msg.setStandardButtons(standardButtons)
        if defaultButton:
            msg.setDefaultButton(defaultButton)
        return msg.exec()


if __name__ == '__main__':
    logging.config.fileConfig('./config/logging.cfg')
    app = QApplication(sys.argv)
    window = DataManageUI()
    window.show()
    sys.exit(app.exec())
