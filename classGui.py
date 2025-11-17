#coding:utf-8
##	@package classGUI
#	GUI 表示/管理するスクリプト

import os
from tkinter import *
from tkinter import ttk
from tkinter import messagebox as tkMessageBox
import	threading
import time
import datetime
import queue
import classSerial
import classPacket
import csv

DEF_SETTING_FILENAME = "setting.txt"
DEF_APP_TITLE = "Logical Product Application"
DEF_INITIAL_PORTPATH='COM5'
DEF_LOGTEXT_MAX = 64 # ログ表示行数を増加

TARGET_SENSOR_IDS = {11, 12, 13} 
CONNECTION_CHECK_TIMEOUT_MS = 3000

# (モード名, モードコード, 要求サンプリング周波数(Hz)) のタプルのリスト
ALL_TEST_MODES = [
    # 個別制御通常モード (p.8)
    ("通常 (メモリ記録あり)", 0x00, 200),
    ("通常 (メモリ記録なし)", 0x01, 200),
    # 複数波形通常モード (p.9)
    ("10Hzサンプリング/2Hz送信", 0x12, 10),
    ("20Hzサンプリング/4Hz送信", 0x22, 20),
    ("50Hzサンプリング/10Hz送信", 0x32, 50),
    ("100Hzサンプリング/20Hz送信", 0x42, 100),
    ("200Hzサンプリング/40Hz送信", 0x52, 200),
    # 複数波形1kHz間引モード (p.10)
    ("1kHzサンプリング/2Hz送信", 0x14, 1000),
    ("1kHzサンプリング/4Hz送信", 0x24, 1000),
    ("1kHzサンプリング/10Hz送信", 0x34, 1000),
    ("1kHzサンプリング/20Hz送信", 0x44, 1000),
    ("1kHzサンプリング/40Hz送信", 0x54, 1000),
    # 複数波形200Hz間引モード (p.10)
    ("200Hzサンプリング/10Hz送信", 0x16, 200),
    ("200Hzサンプリング/20Hz送信", 0x26, 200),
    ("200Hzサンプリング/50Hz送信", 0x36, 200),
    ("200Hzサンプリング/100Hz送信", 0x46, 200),
]

FAILED_MODES_NO_REC_TEST = [
    ("100Hz/20Hz (記録なし)", 0x43, 100),
    ("200Hz/40Hz (記録なし)", 0x53, 200),
    ("1kHz/20Hz (記録なし)", 0x45, 1000),
    ("1kHz/40Hz (記録なし)", 0x55, 1000),
    ("200Hz/100Hz (記録なし)", 0x47, 200),
]

class LogText:
    def __init__(self,txt): self.mDate = datetime.datetime.now(); self.mText = txt
    def getLog( self, isDisplayTime ):
        return f"{self.mDate.strftime('%H:%M:%S')} > {self.mText}" if isDisplayTime else f" > {self.mText}"

class SendCommand:
    def __init__(self, name, cmd_id): self.mName = name; self.mCommandId = cmd_id
		
class EasyButton(Button):
    def __init__(self,master=None, **kwargs): super().__init__(master, **kwargs)
    def Enable(self): self.config(state='normal')
    def Disable(self): self.config(state='disabled')

class AppFrame(Frame):
    def __init__(self, master=None):
        super().__init__(master)
        self.master.title(DEF_APP_TITLE)
        self.SerialPort = classSerial.SerialPort()
        self.receive_queue = queue.Queue()
        self.initializeData()
        self.setupGUI()
        self.bind("<Destroy>", self.eventHandlerDestroy)
        self.loadSetting()
        self.master.after(100, self.process_queue)
        self.master.after(50, self.process_data_buffer)

    def process_data_buffer(self):
        try:
            if not self.csv_writer: return
            all_sensors_updated = all(
                (self.latest_received_seqs.get(s_id, -1) > self.last_written_seqs.get(s_id, -1)) or \
                (self.last_written_seqs.get(s_id, -1) > 65000 and self.latest_received_seqs.get(s_id, -1) < 1000)
                for s_id in TARGET_SENSOR_IDS
            )
            if all_sensors_updated and self.data_buffer:
                self.data_buffer.sort(key=lambda x: x['timestamp'])
                for row in self.data_buffer: self.csv_writer.writerow(row)
                for row in self.data_buffer:
                    self.last_written_seqs[row['sensor_id']] = max(self.last_written_seqs.get(row['sensor_id'], -1), row['seq'])
                self.data_buffer.clear()
        finally:
            self.master.after(50, self.process_data_buffer)

    def process_queue(self):
        try:
            while not self.receive_queue.empty():
                raw_data = self.receive_queue.get_nowait()
                results_list = classPacket.AnalyzePacketThread(raw_data)
                
                for resultDic in results_list:
                    if not resultDic: continue

                    # モードテスト中の処理
                    if (hasattr(self, 'is_testing_modes') and self.is_testing_modes and
                        'ack' in resultDic and resultDic['ack'].mCommandId == classPacket.DEF_SENDCOMMAND_ID_PREPMEASURE):
                        ack = resultDic['ack']
                        if self.current_testing_mode_code not in self.test_results:
                            if ack.isSuccess():
                                self.test_results[self.current_testing_mode_code] = "成功 (利用可能)"
                            else:
                                self.test_results[self.current_testing_mode_code] = f"失敗 (Status: {hex(ack.mAckStatus)})"

                    target_id = 0
                    if 'ack' in resultDic and resultDic['ack']: target_id = resultDic['ack'].mTargetSensorModuleId
                    elif 'dat' in resultDic and resultDic['dat']: target_id = resultDic['dat'].mTargetSensorModuleId
                    log_prefix = f"[ID:{target_id}] "

                    if self.is_checking_connections and target_id in TARGET_SENSOR_IDS and target_id not in self.responded_sensors:
                        self._addLog_main_thread(f"{log_prefix}接続確認 応答あり")
                        self.responded_sensors.add(target_id)
                        self.sensor_statuses[target_id] = "OK"
                        self.updateSensorStatusGUI()
                        if self.responded_sensors == TARGET_SENSOR_IDS:
                            self.is_checking_connections = False
                            if self.connection_check_timer: self.master.after_cancel(self.connection_check_timer)
                            self._addLog_main_thread("全ての対象センサーの接続を確認しました。")
                            self.buttonSendCmd.Enable()

                    if 'ack' in resultDic:
                        ack = resultDic['ack']
                        self._addLog_main_thread(log_prefix + ack.getString())
                        if self.is_waiting_for_prep_ack and ack.mCommandId == classPacket.DEF_SENDCOMMAND_ID_PREPMEASURE:
                            self.waiting_prep_ack_ids.discard(target_id)
                            if not ack.isSuccess(): self.is_waiting_for_prep_ack = False
                            if self.is_waiting_for_prep_ack and not self.waiting_prep_ack_ids:
                                self.is_waiting_for_prep_ack = False
                                self._addLog_main_thread("全対象の準備完了。計測開始コマンドを送信します。")
                                start_cmd = classPacket.getSendCommand(classPacket.DEF_SENDCOMMAND_ID_STARTMEASURE, 0xFF, measureMode=self.selected_measure_mode)
                                self.SerialPort.send(start_cmd)
                        elif self.is_downloading and ack.mCommandId == classPacket.DEF_SENDCOMMAND_ID_GETFILEDATA and ack.mTargetSensorModuleId == self.download_info['id']:
                            self._addLog_main_thread(f"{log_prefix}ファイルダウンロード完了。")
                            self.save_downloaded_data()

                    if 'dat' in resultDic:
                        dat = resultDic['dat']
                        if isinstance(dat, classPacket.CDataPacket_StartMeasure):
                            if self.csv_writer:
                                csv_data = dat.get_csv_data()
                                if csv_data:
                                    csv_data['timestamp'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                                    self.data_buffer.append(csv_data)
                                    self.latest_received_seqs[dat.mTargetSensorModuleId] = dat.mSequenceNo
                        elif self.is_downloading and isinstance(dat, classPacket.CDataPacket_GetFileData):
                             self._addLog_main_thread(log_prefix + dat.getResultByString())
                             self.download_buffer.extend(dat.get_csv_data())
                        elif isinstance(dat, classPacket.CDataPacket_GetStatusInfo):
                            self._addLog_main_thread(log_prefix + dat.getResultByString())
                        else: self._addLog_main_thread(log_prefix + dat.getResultByString().replace('\n', '\n  '))
                        if hasattr(dat, 'PrintValues'): print(log_prefix, end=""); dat.PrintValues()
        finally:
            self.master.after(100, self.process_queue)

    def initializeData(self):
        self.sendCmdList = [
            SendCommand('ステータス情報取得', classPacket.DEF_SENDCOMMAND_ID_GETSTATUSINFO),
            SendCommand('計測開始', classPacket.DEF_SENDCOMMAND_ID_STARTMEASURE),
            SendCommand('計測終了', classPacket.DEF_SENDCOMMAND_ID_ENDMEASURE),
            SendCommand('メモリからファイル取得', classPacket.DEF_SENDCOMMAND_ID_GETFILEDATA)
        ]
        self.StringPortName = StringVar(value=DEF_INITIAL_PORTPATH)
        self.mbIsLogAddTime = BooleanVar(value=True)
        self.ListLog = []
        self.is_waiting_for_prep_ack = False; self.waiting_prep_ack_ids = set()
        self.is_checking_connections = False; self.responded_sensors = set()
        self.sensor_statuses = {s_id: "未確認" for s_id in TARGET_SENSOR_IDS}
        self.connection_check_timer = None
        self.csv_file = None; self.csv_writer = None
        self.data_buffer = []; self.last_written_seqs = {}; self.latest_received_seqs = {}
        # 実際に利用可能なモードのみを辞書として定義
        self.measure_modes = {
            "通常 (メモリ記録あり)": 0x00,
            "通常 (メモリ記録なし)": 0x01,
            "10Hzサンプリング/2Hz送信": 0x12,
            "20Hzサンプリング/4Hz送信": 0x22,
            "50Hzサンプリング/10Hz送信": 0x32,
            "1kHzサンプリング/2Hz送信": 0x14,
            "1kHzサンプリング/4Hz送信": 0x24,
            "1kHzサンプリング/10Hz送信": 0x34,
            "200Hzサンプリング/10Hz送信": 0x16,
            "200Hzサンプリング/20Hz送信": 0x26,
            "200Hzサンプリング/50Hz送信": 0x36
        }
        self.selected_measure_mode = 0x01 # デフォルトモード
        self.is_downloading = False
        self.download_buffer = []
        self.download_info = {}
        self.is_testing_modes = False
        self.current_testing_mode_code = None

    def loadSetting( self ):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "setting.txt")
        try:
            with open(path, 'r') as fh:
                for l in (line.strip() for line in fh):
                    if not l or l.startswith('#'):
                        continue
                    parts = l.split(',')
                    if len(parts) < 2:
                        continue
                    tag, value = parts[0], parts[1]
                    if tag == "PORT_PATH":
                        self.StringPortName.set(value)
                    elif tag == "GUI_LOGMAX":
                        global DEF_LOGTEXT_MAX
                        DEF_LOGTEXT_MAX = int(value)
        except FileNotFoundError:
            pass

    def setupGUI(self):
        frameLeft = Frame(self); frameLeft.pack(side=LEFT, padx=5, pady=5)
        self.createWidgetPortFrame(frameLeft)
        self.createWidgetSensorStatusFrame(frameLeft)
        self.createWidgetSendCommandFrame(frameLeft)
        frameRight = Frame(self); frameRight.pack(padx=5, pady=5)
        self.createWidgetFrameLog(frameRight)
        self.buttonSendCmd.Disable(); self.buttonCheckConnections.Disable()

    def createWidgetPortFrame(self,parentFrame):
        frameDevice = Frame(parentFrame); frameDevice.pack(side=TOP, fill=X, pady=5)
        Button(frameDevice, text="アプリ終了",command=self.pushButtonDestory).pack()
        framePort = LabelFrame(parentFrame, text="ハードウェア設定"); framePort.pack(fill=X, pady=5)
        frameDevPath = Frame(framePort); frameDevPath.pack(pady=2, padx=5)
        Label(frameDevPath, text="パス:").grid(column=0, row=0, sticky=W)
        self.EntryPortName = Entry(frameDevPath, textvariable=self.StringPortName, width=20)
        self.EntryPortName.grid(column=1, row=0, sticky=W)
        frameDevState = Frame(framePort); frameDevState.pack(pady=2)
        self.LabelPortStatus = Label(frameDevState, text="未接続", width=10); self.LabelPortStatus.grid(column=0, row=0)
        self.ButtonPortOpenClose = Button(frameDevState, text="Port Open", command=self.pushButtonSerialPortOpenClose)
        self.ButtonPortOpenClose.grid(column=1, row=0)
        
    def createWidgetSensorStatusFrame(self, parentFrame):
        statusFrame = LabelFrame(parentFrame, text="センサー接続状態"); statusFrame.pack(fill=X, pady=5, padx=5)
        self.sensor_status_labels = {}
        for i, s_id in enumerate(sorted(list(TARGET_SENSOR_IDS))):
            Label(statusFrame, text=f"ID {s_id}:").grid(row=i, column=0, sticky=W)
            lbl = Label(statusFrame, text="未確認", width=10, fg="gray"); lbl.grid(row=i, column=1, sticky=W)
            self.sensor_status_labels[s_id] = lbl
        self.buttonCheckConnections = EasyButton(statusFrame, text='接続確認', command=self.pushButtonCheckConnections)
        self.buttonCheckConnections.grid(row=len(TARGET_SENSOR_IDS), columnspan=2, pady=5)

    def createWidgetSendCommandFrame(self,parentFrame):
        frame = LabelFrame(parentFrame, text="送信コマンド関連"); frame.pack(fill=X, pady=5)
        modeFrame = Frame(frame); modeFrame.pack(pady=2)
        Label(modeFrame, text="計測モード:").pack(side=LEFT)
        self.comboMeasureMode = ttk.Combobox(modeFrame, values=list(self.measure_modes.keys()), width=30, state='readonly')
        self.comboMeasureMode.pack(side=LEFT); self.comboMeasureMode.current(0)
        self.comboMeasureMode.bind('<<ComboboxSelected>>', self.on_measure_mode_selected)
        
        self.ListBoxForCmd = Listbox(frame, height=4, width=38); self.ListBoxForCmd.pack(pady=5)
        for cmd in self.sendCmdList: self.ListBoxForCmd.insert(END, cmd.mName)
        self.ListBoxForCmd.selection_set(0)
        
        fileFrame = Frame(frame); fileFrame.pack(pady=2, anchor=W)
        Label(fileFrame, text="ターゲットID:").pack(side=LEFT)
        self.SpinboxTargetSenssorModule = Spinbox(fileFrame, from_=1, to=254, width=5)
        self.SpinboxTargetSenssorModule.pack(side=LEFT, padx=5)
        Label(fileFrame, text="ファイル番号:").pack(side=LEFT)
        self.SpinboxFileNo = Spinbox(fileFrame, from_=0, to=254, width=5)
        self.SpinboxFileNo.pack(side=LEFT, padx=5)
        
        self.buttonSendCmd = EasyButton(frame, text='Send Command', command=self.pushButtonSendCmd)
        self.buttonSendCmd.pack(anchor=S, pady=5)

        self.buttonTestModes = EasyButton(frame, text='全モード可用性テスト', command=self.start_mode_availability_test)
        self.buttonTestModes.pack(anchor=S, pady=5)
        self.buttonTestFailedModes = EasyButton(
        frame, 
        text='失敗したモードを「記録なし」で再テスト', 
        command=self.start_failed_modes_test
        )
        self.buttonTestFailedModes.pack(anchor=S, pady=5)

    def on_measure_mode_selected(self, event):
        selected_text = self.comboMeasureMode.get()
        self.selected_measure_mode = self.measure_modes[selected_text]
        self._addLog_main_thread(f"計測モード変更: {selected_text}")

    def createWidgetFrameLog(self,parentFrame):
        frame = LabelFrame(parentFrame, text="ログ"); frame.pack(side=RIGHT)
        cframe = Frame(frame); cframe.grid(column=0, row=0, sticky=W)
        self.CheckButtonLogTimeDisplay = Checkbutton(cframe, text="時間表示", variable=self.mbIsLogAddTime, command=self.updateMessage)
        self.CheckButtonLogTimeDisplay.pack(side=LEFT)
        self.textDisplayLog = Text(frame, width=70, height=20, bg='#eeeeee'); self.textDisplayLog.grid(column=0, row=1, sticky="nsew")
        scroll = Scrollbar(frame, orient='vertical', command=self.textDisplayLog.yview); scroll.grid(column=1, row=1, sticky="ns")
        self.textDisplayLog.config(yscrollcommand=scroll.set)
				
    def eventHandlerDestroy(self, event): self.SerialPort.stop(); self.close_csv_file()

    def _addLog_main_thread(self, logString):
        if len(self.ListLog) >= DEF_LOGTEXT_MAX: self.ListLog.pop(0)
        self.ListLog.append(LogText(logString)); self.updateMessage()

    def pushButtonSerialPortOpenClose(self):
        if self.SerialPort.isEnableAccess():
            self.SerialPort.stop(); self.ButtonPortOpenClose.config(text="Port Open")
            self.buttonSendCmd.Disable(); self.LabelPortStatus.config(text="未接続")
            self._addLog_main_thread(f"Port Closed: {self.SerialPort.mDeviceName}")
            self.buttonCheckConnections.Disable()
            self.sensor_statuses = {s_id: "未確認" for s_id in TARGET_SENSOR_IDS}; self.updateSensorStatusGUI()
            self.close_csv_file()
        else:
            port_path = self.StringPortName.get()
            if self.SerialPort.start(port_path, self.receive_queue):
                self.ButtonPortOpenClose.config(text="Port Close"); self.LabelPortStatus.config(text="接続中")
                self._addLog_main_thread(f"Port Open Success: {port_path}"); self.buttonCheckConnections.Enable()
            else: tkMessageBox.showerror("Error", f"ポートが開けませんでした: {port_path}")

    def pushButtonCheckConnections(self):
        if not self.SerialPort.isEnableAccess(): return
        self._addLog_main_thread("全対象センサーの接続確認を開始..."); self.is_checking_connections = True
        self.responded_sensors.clear(); self.sensor_statuses = {s_id: "確認中..." for s_id in TARGET_SENSOR_IDS}
        self.buttonSendCmd.Disable(); self.updateSensorStatusGUI()
        self.SerialPort.send(classPacket.getSendCommand(classPacket.DEF_SENDCOMMAND_ID_GETSTATUSINFO, 0xff))
        if self.connection_check_timer: self.master.after_cancel(self.connection_check_timer)
        self.connection_check_timer = self.master.after(CONNECTION_CHECK_TIMEOUT_MS, self.check_connection_timeout)

    def check_connection_timeout(self):
        self.is_checking_connections = False; self.connection_check_timer = None
        all_ok = all(s_id in self.responded_sensors for s_id in TARGET_SENSOR_IDS)
        for s_id in TARGET_SENSOR_IDS:
            if s_id not in self.responded_sensors: self.sensor_statuses[s_id] = "応答なし"
        self.updateSensorStatusGUI()
        if not all_ok: self._addLog_main_thread("タイムアウト: 一部のセンサーから応答がありませんでした。")
        else: self.buttonSendCmd.Enable()

    def updateSensorStatusGUI(self):
        for s_id, label in self.sensor_status_labels.items():
            status = self.sensor_statuses.get(s_id, "N/A")
            colors = {"OK": "green", "応答なし": "red", "確認中...": "blue"}
            label.config(text=status, fg=colors.get(status, "gray"))

    def pushButtonSendCmd(self):
        if not self.SerialPort.isEnableAccess(): return
        try: selectedCmdObj = self.sendCmdList[self.ListBoxForCmd.curselection()[0]]
        except IndexError: tkMessageBox.showwarning("Warning", "コマンドを選択してください"); return
        
        cmd_id = selectedCmdObj.mCommandId
        if cmd_id == classPacket.DEF_SENDCOMMAND_ID_STARTMEASURE:
            if self.is_waiting_for_prep_ack or self.is_downloading: return
            self.open_csv_file("measurement"); self.SerialPort.send(classPacket.getSendCommand(classPacket.DEF_SENDCOMMAND_ID_ENDMEASURE, 0xff))
            self.master.after(200, self.start_prep_measure)
        elif cmd_id == classPacket.DEF_SENDCOMMAND_ID_ENDMEASURE:
            self.close_csv_file(); self.SerialPort.send(classPacket.getSendCommand(cmd_id, 0xFF))
        elif cmd_id == classPacket.DEF_SENDCOMMAND_ID_GETFILEDATA:
            if self.is_downloading: tkMessageBox.showwarning("警告", "現在別のファイルをダウンロード中です。"); return
            try:
                target_id = int(self.SpinboxTargetSenssorModule.get())
                file_no = int(self.SpinboxFileNo.get())
            except ValueError: tkMessageBox.showerror("Error", "IDとファイル番号は数値で入力してください。"); return
            self.start_download(target_id, file_no)
        else:
            try: target_id = int(self.SpinboxTargetSenssorModule.get())
            except ValueError: tkMessageBox.showerror("Error", "ターゲットIDを数値で入力してください。"); return
            self.SerialPort.send(classPacket.getSendCommand(cmd_id, target_id))

    def start_prep_measure(self):
        self._addLog_main_thread(f'コマンド送信: 計測準備 (モード: {hex(self.selected_measure_mode)})')
        self.is_waiting_for_prep_ack = True; self.waiting_prep_ack_ids = set(TARGET_SENSOR_IDS)
        prep_cmd = classPacket.getSendCommand(classPacket.DEF_SENDCOMMAND_ID_PREPMEASURE, 0xFF, measureMode=self.selected_measure_mode)
        self.SerialPort.send(prep_cmd)

    def start_download(self, target_id, file_no):
        self.is_downloading = True
        self.download_buffer.clear()
        self.download_info = {'id': target_id, 'file': file_no}
        self._addLog_main_thread(f"コマンド送信: ファイル取得 (ID:{target_id}, File:{file_no})")
        download_cmd = classPacket.getSendCommand(classPacket.DEF_SENDCOMMAND_ID_GETFILEDATA, target_id, fileNo=file_no)
        self.SerialPort.send(download_cmd)

    def save_downloaded_data(self):
        if not self.download_buffer:
            self._addLog_main_thread("ダウンロードデータが空のため、ファイルは保存されませんでした。"); self.is_downloading = False; return
        
        info = self.download_info
        filename = f"download_ID{info['id']:02d}_File{info['file']:03d}_{datetime.datetime.now():%Y%m%d_%H%M%S}.csv"
        self._addLog_main_thread(f"ダウンロードしたデータを保存します: {filename}")
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                fieldnames = ['sensor_id', 'seq', 'acc_x', 'acc_y', 'acc_z', 'gyro_x', 'gyro_y', 'gyro_z', 'quat_w', 'quat_x', 'quat_y', 'quat_z']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self.download_buffer)
            self._addLog_main_thread("保存が完了しました。")
        except IOError as e:
            self._addLog_main_thread(f"CSVファイル保存エラー: {e}")
        
        self.is_downloading = False; self.download_buffer.clear(); self.download_info = {}

    def open_csv_file(self, prefix):
        self.close_csv_file()
        filename = f"{prefix}_{datetime.datetime.now():%Y-%m-%d_%H-%M-%S}.csv"
        self._addLog_main_thread(f"CSVファイルを開きます: {filename}")
        try:
            self.csv_file = open(filename, 'w', newline='', encoding='utf-8')
            fieldnames = ['timestamp', 'sensor_id', 'seq', 
                          'acc_x', 'acc_y', 'acc_z', 
                          'gyro_x', 'gyro_y', 'gyro_z', 
                          'mag_x', 'mag_y', 'mag_z',   #  <- この行を追加
                          'quat_w', 'quat_x', 'quat_y', 'quat_z']
            self.csv_writer = csv.DictWriter(self.csv_file, fieldnames=fieldnames)
            self.csv_writer.writeheader()
        except IOError as e: self._addLog_main_thread(f"CSVファイル作成エラー: {e}"); self.csv_file = self.csv_writer = None

    def close_csv_file(self):
        if self.csv_writer and self.csv_file:
            if self.data_buffer:
                self.data_buffer.sort(key=lambda x: x['timestamp'])
                for row in self.data_buffer: self.csv_writer.writerow(row)
                self.data_buffer.clear()
            self._addLog_main_thread(f"CSVファイルを閉じます: {self.csv_file.name}")
            self.csv_file.close()
        self.csv_file = self.csv_writer = None

    def pushButtonDestory(self): self.master.destroy()
		
    def updateMessage(self):
        self.textDisplayLog.config(state='normal')
        self.textDisplayLog.delete('1.0', 'end')	
        for log in self.ListLog: self.textDisplayLog.insert('end', log.getLog(self.mbIsLogAddTime.get()) + "\n")
        self.textDisplayLog.see('end'); self.textDisplayLog.config(state='disabled')

    # --- Mode Test Functions ---
    def start_mode_availability_test(self):
        if not self.SerialPort.isEnableAccess():
            tkMessageBox.showwarning("警告", "ポートが開かれていません。")
            return
        
        self.test_modes_list = ALL_TEST_MODES
        self.test_results = {}
        self.current_test_index = 0

        self._addLog_main_thread("====== 全計測モードの可用性テストを開始します ======")
        self._addLog_main_thread("各モードに必要なサンプリング周波数を自動設定します。")
        self.is_testing_modes = True
        
        self.run_next_mode_test()

    def run_next_mode_test(self):
        if self.current_test_index >= len(self.test_modes_list):
            self.finish_mode_test()
            return

        mode_name, mode_code, required_freq = self.test_modes_list[self.current_test_index]
        self.current_testing_mode_code = mode_code
        
        self._addLog_main_thread(f"--- テスト中 [{self.current_test_index + 1}/{len(self.test_modes_list)}]: '{mode_name}' ---")
        
        self._addLog_main_thread(f"ステップ1: サンプリング周波数を {required_freq}Hz に設定します...")
        freq_cmd = classPacket.getSendCommand(
            classPacket.DEF_SENDCOMMAND_ID_SETSAMPLING,
            0xFF, 
            samplingFrequency=required_freq
        )
        self.SerialPort.send(freq_cmd)

        self.master.after(2000, self.send_prep_for_test, mode_name, mode_code)

    def send_prep_for_test(self, mode_name, mode_code):
        self._addLog_main_thread("ステップ2: 計測準備コマンドを送信します...")
        prep_cmd = classPacket.getSendCommand(
            classPacket.DEF_SENDCOMMAND_ID_PREPMEASURE, 
            0xFF,
            measureMode=mode_code
        )
        self.SerialPort.send(prep_cmd)

        # 応答を待つ時間
        self.master.after(1000, self.reset_sensor_state_for_test)

    def reset_sensor_state_for_test(self):
        # 計測準備状態をリセットするために計測停止コマンドを送信
        self._addLog_main_thread("ステップ3: センサー状態をリセットします...")
        stop_cmd = classPacket.getSendCommand(classPacket.DEF_SENDCOMMAND_ID_ENDMEASURE, 0xFF)
        self.SerialPort.send(stop_cmd)
        
        # 次のテストへ (リセットのための時間も考慮)
        self.master.after(2000, self.run_next_mode_test)
        self.current_test_index += 1

    def finish_mode_test(self):
        self.is_testing_modes = False
        self._addLog_main_thread("====== 全てのモードのテストが完了しました ======")
        
        self._addLog_main_thread("【テスト結果】")
        for mode_name, mode_code, freq in self.test_modes_list:
            result = self.test_results.get(mode_code, "応答なし")
            log_msg = f"モード '{mode_name}' ({hex(mode_code)}, {freq}Hz): {result}"
            self._addLog_main_thread(log_msg)
        
        self.SerialPort.send(classPacket.getSendCommand(classPacket.DEF_SENDCOMMAND_ID_ENDMEASURE, 0xFF))
        self._addLog_main_thread("サンプリング周波数を200Hzに戻します。")
        freq_cmd = classPacket.getSendCommand(classPacket.DEF_SENDCOMMAND_ID_SETSAMPLING, 0xFF, samplingFrequency=200)
        self.SerialPort.send(freq_cmd)

    def start_failed_modes_test(self):
        if not self.SerialPort.isEnableAccess():
            tkMessageBox.showwarning("警告", "ポートが開かれていません。")
            return
        
        # 今回は新しいテストリストを参照する
        self.test_modes_list = FAILED_MODES_NO_REC_TEST
        self.test_results = {}
        self.current_test_index = 0

        self._addLog_main_thread("====== 失敗モードの「記録なし」での再テストを開始します ======")
        self.is_testing_modes = True
        
        self.run_next_mode_test()        

if __name__ == "__main__":
    root = Tk()
    AppFrame(master=root).pack()
    root.mainloop()