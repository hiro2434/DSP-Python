# coding:utf-8
## @package classSerial
#
#	シリアルポートクラス (スレッドセーフ版)
#
import serial
import threading
import queue
import time

## シリアルポート管理クラス (専用ワーカースレッドを持つ)
class SerialPort(object):
    def __init__(self):
        self.mHandle = None
        self.mDeviceName = ""
        self.mBaudRate = 3000000
        self.mTimeOut = 1 # 読み取りタイムアウトは短くする

        # スレッド関連
        self.thread = None
        self.is_running = False
        self.send_queue = queue.Queue()
        self.receive_queue = None # GUI側から渡される

        self.isPrintLog = True

    def isEnableAccess(self):
        return self.mHandle is not None and self.mHandle.is_open and self.is_running

    def start(self, portName, receive_queue):
        if self.isEnableAccess():
            self.printLog("Port is already running.")
            return False

        self.mDeviceName = portName
        self.receive_queue = receive_queue
        
        try:
            self.mHandle = serial.Serial(
                port=self.mDeviceName,
                baudrate=self.mBaudRate,
                timeout=self.mTimeOut,
                rtscts=False # まずはフロー制御なしで試す
            )
            # DTR/RTS制御 (デバイスのリセット防止)
            self.mHandle.dtr = False
            self.mHandle.rts = False
            time.sleep(0.1)
        except serial.SerialException as e:
            self.printLog(f"Error portOpen(): {e}")
            self.mHandle = None
            return False

        self.is_running = True
        self.thread = threading.Thread(target=self._worker_thread)
        self.thread.daemon = True
        self.thread.start()
        self.printLog(f"Serial worker thread started for {self.mDeviceName}")
        return True

    def stop(self):
        if not self.is_running:
            return
        
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=2)
        
        if self.mHandle and self.mHandle.is_open:
            self.mHandle.close()
        
        self.mHandle = None
        self.printLog(f"Serial worker thread stopped for {self.mDeviceName}")

    def send(self, data):
        if not self.is_running:
            return
        self.send_queue.put(data)

    def _worker_thread(self):
        while self.is_running:
            # 送信キューをチェック
            try:
                send_data = self.send_queue.get_nowait()
                self.mHandle.write(send_data)
                self.mHandle.flush()
                self.printLog(f"send: {send_data.hex(' ')}")
            except queue.Empty:
                pass # 送信するものがなければ何もしない
            except Exception as e:
                self.printLog(f"Error in sending data: {e}")

            # 受信を試みる
            try:
                if self.mHandle.in_waiting > 0:
                    read_data = self.mHandle.read(self.mHandle.in_waiting)
                    if self.receive_queue:
                        self.receive_queue.put(read_data)
                    self.printLog(f"receive: {read_data.hex(' ')}")
            except Exception as e:
                self.printLog(f"Error in receiving data: {e}")
                # エラー発生時はスレッドを終了させる
                self.is_running = False
            
            time.sleep(0.01) # CPU負荷を下げるための短い待機

    def printLog(self, strLog):
        if self.isPrintLog:
            print(strLog)