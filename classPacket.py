#coding:utf-8
#
##	@package classPacket
#
#		送受信パケット管理
#		送信コマンドの生成
#		受信コマンドの解析
#
#	バイトオーダー	すべてビッグエンディアン
#


from struct import *	#for pack
import datetime


#
#	定義変数	セクション
#
#プロダクトID定義
DEF_PRODUCT_ID_WirelessMotionSensor9Axis = 0xff
DEF_PRODUCT_ID_WirelessEMGLogger = 0x02
DEF_PRODUCT_ID_WirelessMotionSensor9Axis5G = 0x03
DEF_PRODUCT_ID_AllDevice = 0xff



#コマンドID	定義(必要に応じて追加)
DEF_SENDCOMMAND_ID_GETSTATUSINFO	=	0x05
DEF_SENDCOMMAND_ID_STARTMEASURE		=	0x02
DEF_SENDCOMMAND_ID_ENDMEASURE		=	0x04
DEF_SENDCOMMAND_ID_PREPMEASURE      =   0x1F
DEF_SENDCOMMAND_ID_GETFILEDATA      =   0x09
DEF_SENDCOMMAND_ID_SETSAMPLING      =   0x0B  # サンプリング周波数設定


#ACKステータス(必要に応じて追加)
DEF_ACKSTATUS_CODE_SUCCESS							=	0x21	#コマンド正常
DEF_ACKSTATUS_CODE_IMPOSSIBLE_CREATEFILE			=	0x64	#ファイル作成不可







#	グローバル変数定義	セクション

#共通プロダクトID
#	実行中に、頻繁に変更される変数ではないので、
#	このスクリプト内で管理する
#	基本的に、起動時のみに設定
gProductId = DEF_PRODUCT_ID_WirelessMotionSensor9Axis








#
#	関数定義
#
#




##プロダクトIDの設定
#	@return		なし
#	@param		prodId	:	プロダクトID
def setProductID( prodId ):
    gProductId = prodId

##プロダクトIDの取得
#	@return		プロダクトID
#	@param		なし
def getProductID():
    return gProductId



##	bccの計算
#
#		コマンド番号から　bcc直前バイトまで
#	@return		int		数値
#
#	@param		payload		:チェック対象バッファ
def checkBCC( payload ):
    bcc = 0
    for byte in payload:
        bcc ^= byte
    return bcc




##	文字列→数値変換
#		バッファを指定バイト数分だけ数値に変換する
#
#	@return		int		数値
#	@param		packet		:	受信パケット(文字列)
#	@param		startIdx	:	解析開始要素index
#	@param		length		:	解析長
#
## バイト列から数値に変換 (ビッグエンディアン)
def convertValueByByte(packet, startIdx, length):
    return int.from_bytes(packet[startIdx:startIdx+length], 'big')









##	送信コマンドパケットの取得
#		送信コマンドIDと対象センサーモジュールIDのみを引数にしているが、
#		コマンド追加対応の際には、引数の変更/実装変更が必要
#
#	@return			str	パケット文字列
#
#	@param		sendCommandId			:	送信コマンドID
#	@param		targetSenssorModuleId	：	対象センサーモジュールID
#
def getSendCommand( sendCommandId,targetSenssorModuleId, **kwargs ): # kwargsを追加
    
    #コマンドIDに対応したパケットコマンドを返す
    if sendCommandId == DEF_SENDCOMMAND_ID_GETSTATUSINFO:
        return getSendCommand_GetStatusInfo(targetSenssorModuleId)
    elif sendCommandId == DEF_SENDCOMMAND_ID_STARTMEASURE:
        measureMode = kwargs.get('measureMode', 1)
        return getSendCommand_StartMeasure(targetSenssorModuleId, measureMode, datetime.datetime.now())
    elif sendCommandId == DEF_SENDCOMMAND_ID_PREPMEASURE:
        measureMode = kwargs.get('measureMode', 1)
        return getSendCommand_PrepMeasure(targetSenssorModuleId, measureMode)
    elif sendCommandId == DEF_SENDCOMMAND_ID_ENDMEASURE:
        return getSendCommand_StopMeasure(targetSenssorModuleId)
    elif sendCommandId == DEF_SENDCOMMAND_ID_GETFILEDATA:
        fileNo = kwargs.get('fileNo', 0)
        startSeq = kwargs.get('startSeq', 0)
        numSeq = kwargs.get('numSeq', 0xFFFFFFFF) # デフォルトは最後まで
        return getSendCommand_GetFileData(targetSenssorModuleId, fileNo, startSeq, numSeq)
    elif sendCommandId == DEF_SENDCOMMAND_ID_SETSAMPLING:
        samplingFrequency = kwargs.get('samplingFrequency', 200) # デフォルト200Hz
        return getSendCommand_SetSamplingFrequency(targetSenssorModuleId, samplingFrequency)
    return b""








##	コマンドパケットの取得
#		ステータス情報取得
#
#	@return			str	パケット文字列
#	@param			targetSenssorModuleId	：	対象センサーモジュールID
#
def getSendCommand_GetStatusInfo(targetSenssorModuleId):
    packet = b"\x55\x55"
    
    payload = b""
    payload += pack('>B', gProductId)
    payload += pack('>B', targetSenssorModuleId)
    payload += pack('>B', DEF_SENDCOMMAND_ID_GETSTATUSINFO)
    
    packet += pack('>B', 5) 
    
    packet += payload
    packet += pack('>B', checkBCC(payload))
    packet += b'\xAA'
    
    return packet



##	コマンドパケットの取得
#		計測開始
#
#	@return			str	パケット文字列
#
#	@param		targetSenssorModuleId	：	対象センサーモジュールID
#	@param		measureMode				：	計測モード
#	@param		startTime				：	計測開始時間？	time型
#
def getSendCommand_StartMeasure(targetSenssorModuleId, measureMode, startTime):
    packet = b"\x55\x55"
    
    payload = b""
    payload += pack('>B', gProductId)
    payload += pack('>B', targetSenssorModuleId)
    payload += pack('>B', DEF_SENDCOMMAND_ID_STARTMEASURE)
    payload += pack('>B', startTime.year % 100)
    payload += pack('>B', startTime.month)
    payload += pack('>B', startTime.day)
    payload += pack('>B', startTime.hour)
    payload += pack('>B', startTime.minute)
    payload += pack('>B', measureMode)
    
    packet += pack('>B', 11)
    
    packet += payload
    packet += pack('>B', checkBCC(payload))
    packet += b'\xAA'
    
    return packet


##	コマンドパケットの取得
#		計測停止
#	@return			str	パケット文字列
#
#	@param			targetSenssorModuleId	：	対象センサーモジュールID
#
def getSendCommand_StopMeasure(targetSenssorModuleId):
    packet = b"\x55\x55"
    
    payload = b""
    payload += pack('>B', gProductId)
    payload += pack('>B', targetSenssorModuleId)
    payload += pack('>B', DEF_SENDCOMMAND_ID_ENDMEASURE)
    
    packet += pack('>B', 5)

    packet += payload
    
    # ▼▼▼ 修正: コマンドIDではなくBCCを付与する ▼▼▼
    packet += pack('>B', checkBCC(payload)) 
    # ▲▲▲ ここまで ▲▲▲
    packet += b'\xAA'
    
    return packet

##	コマンドパケットの取得
#		計測準備
#	@return			str	パケット文字列
#	@param			targetSenssorModuleId	：	対象センサーモジュールID
def getSendCommand_PrepMeasure(targetSenssorModuleId, measureMode): # measureModeを追加
    packet = b"\x55\x55"

    payload = b""
    payload += pack('>B', gProductId)
    payload += pack('>B', targetSenssorModuleId)
    payload += pack('>B', DEF_SENDCOMMAND_ID_PREPMEASURE)
    payload += b'\x00' # 予約バイト

    payload += b'\x00' * 13

    payload += pack('>B', measureMode)

    payload += b'\x00' * 4
    payload += b'\x00' * 64
    payload += b'\x00' * 4
    payload += b'\x00' * 6

    packet += pack('>B', 98)
    packet += payload
    packet += pack('>B', checkBCC(payload))
    packet += b'\xAA'
    
    return packet


##	コマンドパケットの取得		(確認済み)
#		ファイルデータ取得
#
#	@return			str	パケット文字列
#
#	@param		targetSenssorModuleId	：	対象センサーモジュールID
#	@param		fileNo					：	ファイル番号
#	@param		startSequenceNo			：	開始シーケンス番号
#	@param		sequenceNum				：	シーケンス数
#
def getSendCommand_GetFileData( targetSenssorModuleId, fileNo, startSequenceNo, sequenceNum ):
    packet = b"\x55\x55"

    payload = b""
    payload += pack('>B', gProductId)
    payload += pack('>B', targetSenssorModuleId)
    payload += pack('>B', DEF_SENDCOMMAND_ID_GETFILEDATA)
    payload += pack('>B', fileNo)
    # バイトオーダーをビッグエンディアン ">" に統一
    payload += pack('>I', startSequenceNo) 
    payload += pack('>I', sequenceNum)
    
    # 残りバイト数は 14 (0x0E)
    packet += pack('>B', 14)
    packet += payload
    packet += pack('>B', checkBCC(payload))
    packet += b"\xaa"

    return packet


##	コマンドパケットの取得
#		サンプリング周波数設定
#
#	@return			str	パケット文字列
#	@param			targetSenssorModuleId	：	対象センサーモジュールID
#	@param			samplingFrequency		：	設定する周波数(Hz)
#
def getSendCommand_SetSamplingFrequency(targetSenssorModuleId, samplingFrequency):
    packet = b"\x55\x55"
    
    payload = b""
    payload += pack('>B', gProductId)
    payload += pack('>B', targetSenssorModuleId)
    payload += pack('>B', DEF_SENDCOMMAND_ID_SETSAMPLING)
    payload += pack('>H', samplingFrequency) # 周波数は2バイト(Short)
    
    packet += pack('>B', 7) # 残りバイト数
    
    packet += payload
    packet += pack('>B', checkBCC(payload))
    packet += b'\xAA'
    
    return packet


#
# ここから下の未確認関数は元のままです
#

##	コマンドパケットの取得		(未確認)
#		ファイル情報取得
#
#	@return			str	パケット文字列
#
#	@param		targetSenssorModuleId	：	対象センサーモジュールID
#
def getSendCommand_GetFileInformation( targetSenssorModuleId ):
    packet = b""
    packet += b"\x55\x55"
    packet += pack( '>b', 5 )
    packet += gProductId#pack( '>b', gProductId )
    packet += targetSenssorModuleId#pack( '>b', targetSenssorModuleId )
    packet += pack( '>b', 7 )	
    packet += pack( '>b', checkBCC( packet,5,len(packet)-5 ))
    packet += b"\xaa"

    return packet

##	コマンドパケットの取得	(未確認)
#		ファイルコメント取得
#	@return		str:	パケット文字列
#
#	@param		targetSenssorModuleId	：	対象センサーモジュールID
#	@param		fileNo					：	ファイル番号
#
def getSendCommand_GetFileComment( targetSenssorModuleId, fileNo ):
    packet = b""
    packet += "\x55\x55"
    packet += pack( '>b', 7 )
    packet += gProductId#pack( '>b', gProductId )
    packet += targetSenssorModuleId#pack( '>b', targetSenssorModuleId )
    packet += pack( '>b', 29 )
    packet += pack( '>b', int(fileNo*2/8) )
    packet += pack( '>b', int(fileNo*2%8) )
    packet += pack( '>b', checkBCC( packet,5,len(packet)-5 ))
    packet += "\xaa"

    return packet

##	コマンドパケットの取得		(未確認)
#		設定初期化
#	@return			str	パケット文字列
#	@param			targetSenssorModuleId	：	対象センサーモジュールID 
#
def getSendCommand_ResetSetting( targetSenssorModuleId ):
    packet = b""
    packet += "\x55\x55"
    packet += pack( '>b', 5 )
    packet += gProductId#pack( '>b', gProductId )
    packet += targetSenssorModuleId#pack( '>b', targetSenssorModuleId )
    packet += pack( '>b', 17 )
    packet += pack( '>b', checkBCC( packet,5,len(packet)-5 ))
    packet += "\xaa"

    return packet


##	コマンドパケットの取得		(未確認)
#		シリアル番号取得
#
#	@return			str	パケット文字列
#	@param			targetSenssorModuleId	：	対象センサーモジュールID 
#
def getSendCommand_GetSerialNo( targetSenssorModuleId ):
    packet = b""
    packet += "\x55\x55"
    packet += pack( '>b', 5 )
    packet += gProductId#pack( '>b', gProductId )
    packet += targetSenssorModuleId#pack( '>b', targetSenssorModuleId )
    packet += pack( '>b', 20 )
    packet += pack( '>b', checkBCC( packet,5,len(packet)-5 ))
    packet += "\xaa"

    return packet


##	コマンドパケットの取得		(未確認)
#		ファームウェアバージョン取得
#
#	@return		str	パケット文字列
#	@param		targetSenssorModuleId	：	対象センサーモジュールID 
#
def getSendCommand_GetFirmwareVersionNo( targetSenssorModuleId ):
    packet = b""
    packet += "\x55\x55"
    packet += pack( '>b', 5 )
    packet += gProductId#pack( '>b', gProductId )
    packet += targetSenssorModuleId#pack( '>b', targetSenssorModuleId )
    packet += pack( '>b', 19 )
    packet += pack( '>b', checkBCC( packet,5,len(packet)-5 ))
    packet += "\xaa"

    return packet


##	コマンドパケットの取得		(未確認)
#		ハードウェアバージョン取得
#
#	@return		str	パケット文字列
#	@param		targetSenssorModuleId	：	対象センサーモジュールID 
#
def getSendCommand_GetHardwareVersionNo( targetSenssorModuleId ):
    packet = b""
    packet += "\x55\x55"
    packet += pack( '>b', 5 )
    packet += gProductId#pack( '>b', gProductId )
    packet += targetSenssorModuleId#pack( '>b', targetSenssorModuleId )
    packet += pack( '>b', 22 )
    packet += pack( '>b', checkBCC( packet,5,len(packet)-5 ))
    packet += "\xaa"

    return packet


##	ACKパケットオブジェクト
#	
#
class ACKPacket(object):
    def Analyze( self,packet ):
        self.mBytesLen = packet[2]
        self.mProductId = packet[4]
        self.mTargetSensorModuleId = packet[3]
        self.mResponseCode = packet[5]
        self.mCommandId = self.mResponseCode & 0x7F 
        self.mAckStatus = packet[6]
        self.mBcc = packet[len(packet)-2]
        return self.mBytesLen

    def isSuccess(self):
        return self.mAckStatus == DEF_ACKSTATUS_CODE_SUCCESS

    def getString(self):
        result = f"ACK Packet (for Cmd: {hex(self.mCommandId)}): "
        if self.isSuccess(): result += "正常"
        else: result += f"失敗 (Status: {hex(self.mAckStatus)})"
        return result


##	データパケット	共通部分
#		
#
class CDataPacketCommon(object):
    def __init__(self):
        self.mCommandId = 0; self.mBytesLen = 0; self.mTargetSensorModuleId = 0
        self.mProductId = 0; self.mResponseCode = 0; self.mBcc = 0

    def AnalyzeHeader(self,packet):
        self.mBytesLen = (packet[2])
        self.mTargetSensorModuleId = (packet[3])
        self.mProductId = (packet[4])
        self.mResponseCode = (packet[5])
        self.mBcc = (packet[len(packet)-2])
        return 6

    def Print(self):
        print (f"BytesLen:{self.mBytesLen}, ProdID:{self.mProductId}, "
               f"TargetID:{self.mTargetSensorModuleId}, RespCode:{hex(self.mResponseCode)}")


##	ステータス情報取得
#
#
class CDataPacket_GetStatusInfo(CDataPacketCommon):
    def __init__(self):
        CDataPacketCommon.__init__(self)
        self.mMeasurementHour = 0; self.mMeasurementMin = 0; self.mMeasurementSec = 0
        self.mMeasuringfrequency = 0; self.mRadioChannel = 0; self.mSerialNo = 0
        self.mHardwareVersionNo = 0; self.mMemoryFileCount = 0; self.mBatteryValue = 0

    def Analyze(self,packet):
        CDataPacketCommon.AnalyzeHeader(self,packet)
        self.mMeasurementHour = (packet[7]); self.mMeasurementMin = (packet[8]); self.mMeasurementSec = (packet[9])
        self.mMeasuringfrequency = convertValueByByte(packet, 10, 2)
        self.mRadioChannel = (packet[12])
        self.mSerialNo = convertValueByByte(packet, 13, 5)
        self.mHardwareVersionNo = convertValueByByte(packet, 18, 5)
        self.mMemoryFileCount = (packet[74])
        self.mBatteryValue = (packet[75])
        return self.mBytesLen

    def getResultByString(self):
        return (f"ステータス: 周波数={self.mMeasuringfrequency}Hz, "
                f"ファイル数={self.mMemoryFileCount}, バッテリー={self.mBatteryValue}")


##	計測開始
#
#
class CDataPacket_StartMeasure(CDataPacketCommon):
    def __init__(self):
        CDataPacketCommon.__init__(self)
        self.mBatteryVoltage = 0; self.mSequenceNo = 0; self.sample = {}

    def Analyze(self, packet):
        CDataPacketCommon.AnalyzeHeader(self, packet)
        if self.mProductId != 0x34: self.sample = {}; return self.mBytesLen
        def bytes_to_float(b): return unpack('>f', b)[0]
        self.sample = {}
        try:
            self.mBatteryVoltage = packet[6]
            self.mSequenceNo = convertValueByByte(packet, 7, 2)
            base = 11
            self.sample['gyro_x'] = bytes_to_float(packet[base:base+4]); self.sample['gyro_y'] = bytes_to_float(packet[base+4:base+8]); self.sample['gyro_z'] = bytes_to_float(packet[base+8:base+12])
            self.sample['acc_x'] = bytes_to_float(packet[base+12:base+16]); self.sample['acc_y'] = bytes_to_float(packet[base+16:base+20]); self.sample['acc_z'] = bytes_to_float(packet[base+20:base+24])
            
            # 地磁気データを正しく解析
            self.sample['mag_x'] = bytes_to_float(packet[base+24:base+28]); self.sample['mag_y'] = bytes_to_float(packet[base+28:base+32]); self.sample['mag_z'] = bytes_to_float(packet[base+32:base+36])

            # クォータニオンの正しい開始位置 (base + 36) から解析
            quat_base = base + 36 
            self.sample['quat_w'] = bytes_to_float(packet[quat_base:quat_base+4]); self.sample['quat_x'] = bytes_to_float(packet[quat_base+4:quat_base+8]); self.sample['quat_y'] = bytes_to_float(packet[quat_base+8:quat_base+12]); self.sample['quat_z'] = bytes_to_float(packet[quat_base+12:quat_base+16])
        except Exception as e: print(f"Error analyzing measure packet: {e}"); self.sample = {}
        return self.mBytesLen
        
    def PrintValues(self):
        if not self.sample: return
        print(f"SEQ:{self.mSequenceNo}, "
              f"ACC:({self.sample.get('acc_x',0):.3f},{self.sample.get('acc_y',0):.3f},{self.sample.get('acc_z',0):.3f}), "
              f"GYRO:({self.sample.get('gyro_x',0):.3f},{self.sample.get('gyro_y',0):.3f},{self.sample.get('gyro_z',0):.3f}), "
              f"QUAT:({self.sample.get('quat_w',0):.4f},{self.sample.get('quat_x',0):.4f},{self.sample.get('quat_y',0):.4f},{self.sample.get('quat_z',0):.4f})")

    def getResultByString(self):
        return f"計測データ (SEQ: {self.mSequenceNo}, BAT: {self.mBatteryVoltage})"

    def get_csv_data(self):
        if not self.sample: return None
        return {'sensor_id': self.mTargetSensorModuleId, 'seq': self.mSequenceNo,
                **self.sample}


##	計測終了
#
class CDataPacket_EndMeasure(CDataPacketCommon):
    def Analyze(self,packet): CDataPacketCommon.AnalyzeHeader(self,packet); return 0
    def getResultByString(self): return ""


# ▼▼▼ 修正: ファイルデータ取得クラス ▼▼▼
class CDataPacket_GetFileData(CDataPacketCommon):
    def __init__(self):
        CDataPacketCommon.__init__(self)
        self.packet_no = 0; self.data_count = 0; self.samples = []

    def Analyze(self, packet):
        CDataPacketCommon.AnalyzeHeader(self, packet)
        self.samples = []
        try:
            self.packet_no = convertValueByByte(packet, 6, 4)
            self.data_count = packet[10]
            def bytes_to_float(b): return unpack('>f', b)[0]
            
            # Type E (DSPモーションセンサ) のデータ構造
            SAMPLE_SIZE_BYTES = 40 # acc(12) + gyro(12) + quat(16)
            data_start_base = 11

            for i in range(self.data_count):
                base = data_start_base + (i * SAMPLE_SIZE_BYTES)
                sample = {}
                # データ構造がCDataPacket_StartMeasureと全く同じと仮定して解析
                sample['gyro_x'] = bytes_to_float(packet[base:base+4]); sample['gyro_y'] = bytes_to_float(packet[base+4:base+8]); sample['gyro_z'] = bytes_to_float(packet[base+8:base+12])
                sample['acc_x'] = bytes_to_float(packet[base+12:base+16]); sample['acc_y'] = bytes_to_float(packet[base+16:base+20]); sample['acc_z'] = bytes_to_float(packet[base+20:base+24])
                quat_base = base + 24
                sample['quat_w'] = bytes_to_float(packet[quat_base:quat_base+4]); sample['quat_x'] = bytes_to_float(packet[quat_base+4:quat_base+8]); sample['quat_y'] = bytes_to_float(packet[quat_base+8:quat_base+12]); sample['quat_z'] = bytes_to_float(packet[quat_base+12:quat_base+16])
                self.samples.append(sample)

        except Exception as e:
            print(f"Error analyzing file data packet: {e}"); self.samples = []
        return self.mBytesLen

    def getResultByString(self):
        return f"ファイルデータ受信: PacketNo={self.packet_no}, Samples={len(self.samples)}"

    def get_csv_data(self):
        # GUIでCSV化するために辞書のリストを返す
        csv_list = []
        for i, sample in enumerate(self.samples):
            # ファイルデータにはシーケンス番号が含まれないため、パケット番号とインデックスで代用
            seq_num = (self.packet_no - 1) * self.data_count + i
            csv_list.append({'sensor_id': self.mTargetSensorModuleId, 'seq': seq_num, **sample})
        return csv_list
# ▲▲▲ ここまで ▲▲▲


def checkHeader( byte1,byte2 ): return byte1==0x55 and byte2==0x55
def checkFooter( byte1 ): return byte1==0xAA

def AnalyzePacketThread( packetBufferBytes ):
    results_list = []
    buffer = packetBufferBytes
    while buffer:
        try:
            start_index = buffer.find(b'\x55\x55')
            if start_index == -1: break
            buffer = buffer[start_index:]
            if len(buffer) < 4: break 
            remaining_bytes = buffer[2]
            full_packet_length = 3 + remaining_bytes
            if len(buffer) < full_packet_length: break
            if buffer[full_packet_length - 1] != 0xAA: buffer = buffer[1:]; continue
            packet = buffer[:full_packet_length]
            
            resultDic = {}
            responseCode = packet[5]
            ackPacket = None; dataPacket = None

            if responseCode == 0x85: ackPacket = ACKPacket(); dataPacket = CDataPacket_GetStatusInfo() # ステータスはACKとDATA両方
            elif responseCode == 0x82: ackPacket = ACKPacket()
            elif responseCode == 0x83: dataPacket = CDataPacket_StartMeasure()
            elif responseCode == 0x84: ackPacket = ACKPacket()
            elif responseCode == 0x9F: ackPacket = ACKPacket()
            elif responseCode == 0x89: ackPacket = ACKPacket()
            elif responseCode == 0x8A: dataPacket = CDataPacket_GetFileData()
            else:
                if responseCode & 0x80: ackPacket = ACKPacket()
                else: print(f"!!! Unknown Response Code: {hex(responseCode)} !!!")

            if ackPacket: ackPacket.Analyze(packet); resultDic['ack'] = ackPacket
            if dataPacket: dataPacket.Analyze(packet); resultDic['dat'] = dataPacket
            if resultDic: results_list.append(resultDic)
            buffer = buffer[full_packet_length:]
        except Exception as e: print(f"--- ERROR in AnalyzePacketThread: {e} ---"); break
    return results_list